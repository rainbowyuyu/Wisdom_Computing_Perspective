"""Verified engineering-configuration import owned by Wiscomper.

Reads explicit original-workspace data contracts. Component coordinates never
become wind-farm turbine positions. This module imports and visualizes geometry;
it does not promote a review candidate into an accepted simulation model.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any

from configuration import load_settings
from .schema import Scene

OUTPUTS = Path(__file__).resolve().parents[1] / 'runtime' / 'engineering-imports'
MAX_FILE_BYTES = 32 * 1024 * 1024
CONFIG_PREFIX = 'WISCOMPER_ENGINEERING_'


class EngineeringImportError(ValueError):
    def __init__(self, code: str, message: str):
        self.code=code
        super().__init__(message)


def _integration_settings(settings: dict | None) -> dict:
    return load_settings() if settings is None else settings


def _integration_directory(settings: dict, key: str, explicit: Path | None = None) -> Path | None:
    value = explicit if explicit is not None else settings.get(CONFIG_PREFIX + key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, (str, Path)):
        raise EngineeringImportError('integration_config_invalid', '工程集成目录配置无效，请联系管理员。')
    path = Path(value)
    resolved = path.resolve()
    if not path.is_absolute() or '..' in path.parts or resolved == Path(resolved.anchor):
        raise EngineeringImportError('integration_config_invalid', '工程集成需要明确的绝对目录，不能开放整个磁盘。')
    return resolved


def _integration_profiles(settings: dict) -> dict:
    raw = settings.get(CONFIG_PREFIX + 'PROFILES_JSON')
    if not isinstance(raw, str) or not raw.strip():
        raise EngineeringImportError('integration_unavailable', '尚未配置工程构型来源，请联系管理员；普通可视化仍可使用。')
    try:
        profiles = json.loads(raw)
        if not isinstance(profiles, dict) or not 1 <= len(profiles) <= 16:
            raise ValueError('invalid profile count')
        result = {}
        for ident, profile in profiles.items():
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', ident) or not isinstance(profile, dict):
                raise ValueError('invalid profile')
            if set(profile) != {'label', 'kind', 'geometry_path', 'mesh_path'}:
                raise ValueError('invalid profile fields')
            if profile['kind'] not in {'assembly', 'wet_surface'}:
                raise ValueError('unsupported profile kind')
            if not isinstance(profile['label'], str) or not 1 <= len(profile['label']) <= 120:
                raise ValueError('invalid label')
            result[ident] = {**profile, 'geometry_path': _relative_path(profile['geometry_path']),
                            'mesh_path': _relative_path(profile['mesh_path'])}
        return result
    except (ValueError, TypeError, EngineeringImportError) as exc:
        raise EngineeringImportError('integration_config_invalid', '工程构型映射配置无效，请联系管理员检查。') from exc


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _workspace(root: Path, ident: Any) -> Path:
    if not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9]{32}',ident):
        raise EngineeringImportError('invalid_source','workspace_id 必须为已登记的 32 位工程标识。')
    base=root.resolve()
    location=(base/ident/'files').resolve()
    if not location.is_relative_to(base) or not location.is_dir():
        raise EngineeringImportError('source_unavailable','原工程 files 目录不存在。')
    return location


def _relative_path(value: Any) -> str:
    if not isinstance(value,str) or not value or len(value)>500:
        raise EngineeringImportError('invalid_source','来源必须是工程内的相对路径。')
    value=value.replace('\\','/')
    path=PurePosixPath(value)
    if not path.parts or path.is_absolute() or ':' in value or any(part in ('..','') for part in path.parts):
        raise EngineeringImportError('invalid_source','来源路径不得越过原工程目录。')
    if path.parts[0] not in {'geometry','inputs','reports','results','notes','references'}:
        raise EngineeringImportError('invalid_source','来源只允许工程的几何、输入、报告与证据目录。')
    return str(path)


def _read(base: Path, relative: str, role: str, expected: str|None=None, *, json_value=True) -> tuple[Any,dict,bytes]:
    relative=_relative_path(relative)
    path=(base/relative).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file():
        raise EngineeringImportError('source_unavailable','来源文件不存在或已越过工程目录：'+relative)
    if path.stat().st_size>MAX_FILE_BYTES:
        raise EngineeringImportError('source_too_large','来源文件超过 32 MiB：'+relative)
    raw=path.read_bytes()
    if len(raw)>MAX_FILE_BYTES:
        raise EngineeringImportError('source_too_large','来源文件超过读取限制：'+relative)
    digest=_hash(raw)
    if expected is not None and (not isinstance(expected,str) or expected.lower()!=digest):
        raise EngineeringImportError('source_changed','来源哈希与请求不一致，请重新读取原工程：'+relative)
    try:
        text=raw.decode('utf-8-sig')
        value=json.loads(text) if json_value else text
    except (UnicodeError,ValueError) as exc:
        raise EngineeringImportError('invalid_source','来源不是有效 UTF-8 '+('JSON' if json_value else '文本')+'：'+relative) from exc
    return value,{'path':str(path),'relative_path':relative,'sha256':digest,'bytes':len(raw),'role':role},raw


def _finite(value: Any) -> bool:
    if type(value) not in (int,float):return False
    try:return math.isfinite(value)
    except OverflowError:return False


def _point(value: Any) -> bool:
    return isinstance(value,list) and len(value)==3 and all(_finite(v) and abs(v)<=1e6 for v in value)


def _mesh(mesh: Any) -> dict:
    if not isinstance(mesh,dict) or mesh.get('schema')!='ai-engineer-scene-v1' or mesh.get('units',{}).get('length')!='m':
        raise EngineeringImportError('unsupported_geometry_schema','只支持 ai-engineer-scene-v1 且 length=m 的工程网格。')
    nodes,elements=mesh.get('nodes'),mesh.get('elements')
    if not isinstance(nodes,list) or not 1<=len(nodes)<=250000 or not all(_point(p) for p in nodes):
        raise EngineeringImportError('invalid_geometry','网格节点不是有限的三维米制坐标。')
    if not isinstance(elements,list) or not 1<=len(elements)<=500000:
        raise EngineeringImportError('invalid_geometry','网格单元数量无效。')
    types=mesh.get('types')
    if not isinstance(types,list) or len(types)!=len(elements):
        raise EngineeringImportError('invalid_geometry','网格类型和单元数量不一致。')
    for elem,typ in zip(elements,types):
        if typ not in (5,9) or not isinstance(elem,list) or len(elem)!=(3 if typ==5 else 4):
            raise EngineeringImportError('unsupported_geometry_schema','当前可视化仅接收三角形/四边形表面单元。')
        if any(type(i) is not int or i<0 or i>=len(nodes) for i in elem):
            raise EngineeringImportError('invalid_geometry','单元引用了不存在的节点。')
    return {'node_count':len(nodes),'element_count':len(elements),
            'bounds_m':{'min':[min(p[i] for p in nodes) for i in range(3)],'max':[max(p[i] for p in nodes) for i in range(3)]},
            'source_title':str(mesh.get('title',''))[:400]}


def _components(report: dict, kind: str) -> list[dict]:
    if kind=='wet_surface':
        # A wetted-mesh audit has no assembly component ledger. Do not create one.
        return []
    records=report.get('records')
    if not isinstance(records,list) or not records or len(records)>3000:
        raise EngineeringImportError('unsupported_geometry_schema','装配报告必须包含 records 构件台账。')
    result=[];seen=set()
    for index,row in enumerate(records):
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not _point(row.get('CG_m')):
            raise EngineeringImportError('invalid_geometry','装配构件缺少明确 id 或 CG_m，不能推断位置。')
        if row['id'] in seen:
            raise EngineeringImportError('invalid_geometry','构件标识重复：'+row['id'])
        seen.add(row['id'])
        volume=row.get('volume_m3')
        if volume is not None and (not _finite(volume) or volume<0):
            raise EngineeringImportError('invalid_geometry','构件体积无效：'+row['id'])
        result.append({'id':row['id'],'label':row['id'],'kind':'component_centroid','role':str(row.get('role',''))[:250],
                       'position_m':row['CG_m'],'coordinate_semantics':'center_of_volume_from_CAD_report',
                       'volume_m3':volume,'source_index':index,'source_valid':row.get('valid')})
    return result


def _immutable(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('xb') as handle:
            handle.write(raw)
    except FileExistsError:
        if _hash(path.read_bytes())!=_hash(raw):
            raise EngineeringImportError('artifact_conflict','已有内容寻址证据与源数据不一致，已保留原文件。')


def _memory(context: Any, workspaces: Path | None) -> dict:
    if context is None:return {'items':[],'role':'context_only_not_geometry'}
    if not isinstance(context,dict) or not isinstance(context.get('items',[]),list) or len(context.get('items',[]))>40:
        raise EngineeringImportError('invalid_memory_context','memory_context 应包含至多 40 个来源条目。')
    items=[]
    for raw in context.get('items',[]):
        if not isinstance(raw,dict):continue
        item={k:str(raw.get(k,''))[:(1600 if k=='excerpt' else 500)] for k in ('path','workspace_id','sha256','excerpt','title','kind')}
        item['verification']='unverified_context'
        try:
            if workspaces is None:
                raise EngineeringImportError('integration_unavailable', '未配置工程记忆来源。')
            base=_workspace(workspaces,item['workspace_id'])
            given=Path(item['path'])
            relative=given.resolve().relative_to(base).as_posix() if given.is_absolute() else item['path']
            _,source,_=_read(base,relative,'memory_context',item['sha256'] or None,json_value=False)
            item['source']=source;item['verification']='file_hash_verified'
            # The file hash does not prove a caller's excerpt is a verbatim quote.
            item['excerpt_verification']='not_used_as_geometry_or_numeric_input'
        except (EngineeringImportError,ValueError,OSError):
            item['verification']='unverified_context'
        items.append(item)
    return {'items':items,'role':'context_only_not_geometry','physical_values_extracted':False}


def _preview(components: list[dict], mesh: dict, candidate: str) -> tuple[dict,dict]:
    points=[c['position_m'] for c in components]
    source_kind='component_centroids'
    if not points:
        points=mesh['nodes'];source_kind='sampled_surface_vertices'
    mins=[min(p[i] for p in points) for i in range(3)];maxs=[max(p[i] for p in points) for i in range(3)]
    center=[(a+b)/2 for a,b in zip(mins,maxs)];scale=8/max(1.,max(maxs[i]-mins[i] for i in range(3)))
    # Existing Scene caps 180 objects. The exact mesh is available independently.
    count=min(160,len(points));indexes=sorted({round(i*(len(points)-1)/max(1,count-1)) for i in range(count)})
    objects=[]
    for index in indexes:
        p=points[index]
        # Source CAD z-up -> renderer y-up, proper rotation (x,z,-y).
        x,y,z=(p[0]-center[0])*scale,(p[2]-center[2])*scale,-(p[1]-center[1])*scale
        row=components[index] if components else {}
        objects.append({'id':'source-'+str(index),'kind':'sphere','x':x,'y':y,'z':z,'radius':.045,
                        'label':str(row.get('id','vertex-'+str(index)))[:80],
                        'color':'#D45A58' if str(row.get('id','')).startswith('WT-') else '#2E6AB8'})
    scene=Scene.model_validate({'title':candidate+' · 原工程坐标预览','summary':'显示原工程构件体积中心/顶点采样；完整外形请加载精确网格。点大小只用于识别。',
        'duration':12,'mode':'3d','background':'#F3F6FB','objects':objects,'evidence':'schematic',
        'camera':{'distance':14,'azimuth':.6,'elevation':.22,'orbit':0},
        'assumptions':['原数据为平台本体局部坐标，SWL=0、z轴向上；不是地理坐标或风场机位。',
                       '保留完整原始坐标；视口只做统一比例和坐标轴旋转，不补造构件形状。',
                       f'概览显示 {len(indexes)}/{len(points)} 个点；精确装配网格独立提供，未简化原始证据。'],
        'selection':{'engine':'threejs','category':'spatial','reason':'直接显示可追溯原坐标；不将未绑定CAD当作已求解动力学。'}}).model_dump(mode='json')
    transform={'source_axes':'x,y,z; z-up; SWL=0','viewer_axes':'x,z,-y; y-up','center_source_m':center,'uniform_scale':scale,
               'source_kind':source_kind,'total_points':len(points),'displayed_points':len(indexes),'source_indexes':indexes}
    return scene,transform


def _verified_array_geometry(value: Any, workspaces: Path | None, native_outputs: Path | None) -> tuple[dict,dict]:
    """Read one allowlisted JSON and bind the complete supplied geometry to it."""
    if not isinstance(value,dict) or not isinstance(value.get('source'),dict):
        raise EngineeringImportError('invalid_source','engineering_geometry 需要原始 JSON 的 source.path 与 sha256。')
    source=value['source'];given=source.get('path');digest=source.get('sha256')
    if not isinstance(given,str) or not given or len(given)>1500:
        raise EngineeringImportError('invalid_source','工程几何来源路径无效。')
    if not isinstance(digest,str) or not re.fullmatch(r'[a-f0-9]{64}',digest):
        raise EngineeringImportError('invalid_source','工程几何来源需要小写 SHA256。')
    original=Path(given)
    if not original.is_absolute() or '..' in original.parts or original.suffix.lower()!='.json':
        raise EngineeringImportError('invalid_source','几何来源必须是白名单目录中的绝对 JSON 路径。')
    path=original.resolve()
    workspace_root=workspaces.resolve() if workspaces is not None else None
    native_root=native_outputs.resolve() if native_outputs is not None else None
    allowed=native_root is not None and path.is_relative_to(native_root)
    if workspace_root is not None and path.is_relative_to(workspace_root):
        parts=path.relative_to(workspace_root).parts
        allowed=len(parts)>=4 and bool(re.fullmatch(r'[a-f0-9]{32}',parts[0])) and parts[1:3]==('files','geometry')
    if not allowed:
        raise EngineeringImportError('source_outside_allowed_roots','来源只允许原工程 files/geometry 或 PhysCast outputs/engineering。')
    if not path.is_file():
        raise EngineeringImportError('source_unavailable','工程几何来源文件不存在。')
    limit=4*1024*1024
    if path.stat().st_size>limit:
        raise EngineeringImportError('source_too_large','工程几何 JSON 超过 4 MiB。')
    raw=path.read_bytes()
    if len(raw)>limit:
        raise EngineeringImportError('source_too_large','工程几何 JSON 超过 4 MiB。')
    if _hash(raw)!=digest:
        raise EngineeringImportError('source_changed','工程几何来源 SHA256 已变化，请重新绑定。')
    def unique_object(pairs):
        result={}
        for key,item in pairs:
            if key in result:raise ValueError('duplicate JSON key')
            result[key]=item
        return result
    def invalid_constant(token):
        raise ValueError('non-finite JSON constant: '+token)
    try:
        saved=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=unique_object,parse_constant=invalid_constant)
        if not isinstance(saved,dict):raise ValueError('object required')
        canonical=lambda item:json.dumps(item,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
        supplied={k:v for k,v in value.items() if k!='source'}
        stored={k:v for k,v in saved.items() if k!='source'}
        if canonical(supplied)!=canonical(stored):
            raise EngineeringImportError('geometry_source_mismatch','请求几何与哈希绑定的来源 JSON 不一致；不能显示与计算不同的布局。')
        preserved=json.loads(canonical(value))
    except (UnicodeError,ValueError,TypeError) as exc:
        if isinstance(exc,EngineeringImportError):raise
        raise EngineeringImportError('invalid_source','几何来源必须是有效且无重复键的有限数值 JSON。') from exc
    if (saved.get('schema')!='engineering-geometry-v1' or saved.get('kind')!='turbine_array'
        or saved.get('coordinate_system')!='local_cartesian' or saved.get('units')!='m'):
        raise EngineeringImportError('unsupported_geometry_schema','机位布局只接收 engineering-geometry-v1/turbine_array、local_cartesian 和 m。')
    turbines=saved.get('turbines')
    if not isinstance(turbines,list) or not 1<=len(turbines)<=80:
        raise EngineeringImportError('invalid_geometry','布局预览需要 1—80 个明确机位；不会截断或补造机位。')
    seen=set()
    for row in turbines:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',row['id']):
            raise EngineeringImportError('invalid_geometry','机位需要唯一且有效的 id。')
        if row['id'] in seen:raise EngineeringImportError('invalid_geometry','机位 id 重复。')
        seen.add(row['id'])
        if any(not _finite(row.get(k)) or abs(row[k])>1e6 for k in ('x_m','y_m','z_m')):
            raise EngineeringImportError('invalid_geometry','机位必须提供有限且绝对值不超过 1000000 m 的 x/y/z 坐标。')
        if any(k in row and (not _finite(row[k]) or abs(row[k])>1e6) for k in ('yaw_deg','pitch_deg')):
            raise EngineeringImportError('invalid_geometry','机位姿态必须是有限角度；预览不会自动补齐或裁剪。')
    if 'components' in saved and not isinstance(saved['components'],list):
        raise EngineeringImportError('invalid_geometry','components 如有提供应为数组；布局视图仅显示 turbines。')
    return preserved,{'path':str(path),'sha256':digest,'bytes':len(raw),'role':'unique_turbine_array_geometry',
                      'verification':'full_json_equality_except_source_wrapper'}


def _array_preview(turbines: list[dict], synthetic: bool) -> tuple[dict,dict]:
    mins=[min(row[k] for row in turbines) for k in ('x_m','y_m','z_m')]
    maxs=[max(row[k] for row in turbines) for k in ('x_m','y_m','z_m')]
    center=[(a+b)/2 for a,b in zip(mins,maxs)]
    scale=min(10/max(1.,maxs[0]-mins[0]),5.4/max(1.,maxs[1]-mins[1]),1.)
    objects=[]
    for index,row in enumerate(turbines):
        x=(row['x_m']-center[0])*scale;y=(row['y_m']-center[1])*scale
        location=f"{row['id']} · ({row['x_m']:g}, {row['y_m']:g}, {row['z_m']:g}) m"
        objects.extend([
            {'id':'site-'+str(index),'kind':'circle','x':x,'y':y,'radius':.09,'color':'#1557B0','stroke':'#1557B0','label':location[:80]},
            {'id':'label-'+str(index),'kind':'text','text':row['id'],'x':x,'y':y+.26,'font_size':.2,'color':'#183153'},
        ])
    objects.extend([
        {'id':'scale-bar','kind':'line','points':[[-5,-3.3],[-3,-3.3]],'stroke':'#D14545','line_width':.045},
        {'id':'scale-label','kind':'text','text':f'{2/scale:g} m','x':-4,'y':-3.65,'font_size':.22,'color':'#183153'},
        {'id':'x-axis','kind':'arrow','points':[[4,-3.3],[5,-3.3]],'stroke':'#6B7C93'},
        {'id':'y-axis','kind':'arrow','points':[[4,-3.3],[4,-2.3]],'stroke':'#6B7C93'},
        {'id':'x-label','kind':'text','text':'+X','x':5.25,'y':-3.3,'font_size':.2,'color':'#183153'},
        {'id':'y-label','kind':'text','text':'+Y','x':4,'y':-2.05,'font_size':.2,'color':'#183153'},
    ])
    title=('合成验证样本 · ' if synthetic else '')+'风机机位平面布局'
    scene=Scene.model_validate({'title':title,'summary':'原始米制 x/y 坐标的等比例平面布局；圆点仅表示机位，不代表叶轮、基础、设备外形或仿真结果。',
        'duration':12,'mode':'2d','background':'#F3F6FB','objects':objects,'evidence':'schematic',
        'assumptions':['使用源 JSON 的 x/y 平面投影，完整 z 坐标和姿态仍保留在工程数据中。',
                       '点大小和文字大小仅用于识别，不是设备尺寸；本视图没有工程网格。',
                       '坐标来源验证不等于求解器准入或工程验收；需由 PhysCast 核验完整工程规格。'],
        'selection':{'engine':'canvas2d','category':'spatial','reason':'无CAD外形时，仅按已验证原坐标绘制可追溯的布局标记。'}}).model_dump(mode='json')
    return scene,{'source_axes':'local_cartesian x,y,z','viewer_axes':'x,y; plan projection; z retained in data',
        'center_source_m':center,'uniform_scale':scale,'metres_per_view_unit':1/scale,'bounds_m':{'min':mins,'max':maxs},
        'source_kind':'turbine_locations','total_points':len(turbines),'displayed_points':len(turbines),
        'source_indexes':list(range(len(turbines))),'marker_size_is_physical':False}


def import_turbine_array_design(payload: dict, *, workspaces: Path | None=None,
                                native_outputs: Path | None=None, settings: dict | None=None) -> dict:
    if 'source_geometry' in payload:
        raise EngineeringImportError('conflicting_geometry_sources','不能同时传入 source_geometry 与 engineering_geometry。')
    if set(payload)-{'prompt','engineering_geometry','memory_context','domain'}:
        raise EngineeringImportError('invalid_payload','工程布局导入不接受教学参数；必须使用唯一的结构化几何。')
    if payload.get('domain') not in (None,'wind_farm'):
        raise EngineeringImportError('domain_mismatch','turbine_array 对应 wind_farm，不能改写为单平台或教学风机。')
    prompt=payload.get('prompt','')
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>6000:
        raise EngineeringImportError('invalid_payload','请提供 1—6000 字的布局导入描述。')
    config=_integration_settings(settings)
    workspaces=_integration_directory(config,'WORKSPACES',workspaces)
    native_outputs=_integration_directory(config,'NATIVE_OUTPUTS',native_outputs)
    if workspaces is None and native_outputs is None:
        raise EngineeringImportError('integration_unavailable','尚未配置工程来源目录，请联系管理员；普通可视化仍可使用。')
    geometry,provenance=_verified_array_geometry(payload.get('engineering_geometry'),workspaces,native_outputs)
    turbines=geometry['turbines']
    synthetic='synthetic' in str(geometry.get('evidence_kind','')).lower()
    scene,transform=_array_preview(turbines,synthetic)
    objects=[{'id':row['id'],'label':row['id'],'kind':'turbine_location','position_m':[row['x_m'],row['y_m'],row['z_m']],
              'coordinate_semantics':'source_turbine_site','source_index':index} for index,row in enumerate(turbines)]
    warnings=['仅展示来源机位的平面布局，没有生成或推断风机外形。','布局来源已核验；完整工程规格与求解器适用性仍由 PhysCast 判断。']
    if synthetic:warnings.append('本几何明确标为合成验证样本，不作为连江实际风场机位或工程证明。')
    return {'schema':'world-design-v1','id':'engineering_array_'+provenance['sha256'][:24],'domain':'wind_farm',
        'model_kind':'engineering_configuration','title':scene['title'],'prompt':prompt.strip(),'source':'wiscomper',
        'status':'designed','accepted':False,'parameters':{},'parameter_metadata':{},'objects':objects,'engineering_objects':objects,
        'engineering_geometry':geometry,'scene':scene,'scene_transform':transform,'visualization_kind':'layout_view',
        'constraints':[{'id':'unique_geometry','description':'设计和求解必须共用同一个已核对哈希的完整几何；禁止替换机位。'},
                       {'id':'layout_only','description':'圆点是位置标记，不是设备形状；没有 engineering_mesh。'}],
        'observables':[],'simulation':{'available':False,'reason':'此插件只验证布局来源；完整工程规格需要 PhysCast 独立准入与求解。'},
        'missing_inputs':[],'warnings':warnings,'assumptions':scene['assumptions'],'source_provenance':[provenance],
        'memory_context':_memory(payload.get('memory_context'),workspaces),
        'source_checks':{'source_hash_verified':True,'source_json_equal':True,'source_geometry_unchanged':True,'solver_admission':'not_performed'},
        'design_metadata':{'generator':'wiscomper_verified_turbine_array_import','routing':'explicit_engineering_geometry','paid_model_used':False,
            'geometry_role':'source_turbine_array','source_files':['server/engineering_design.py','server/world_design.py'],
            'renderer':'wiscomper-native-canvas2d','scene_evidence':'source_layout_not_simulation'}}


def import_engineering_design(payload: dict, *, workspaces: Path | None=None, output_root: Path=OUTPUTS,
                              settings: dict | None=None) -> dict:
    source=payload.get('source_geometry')
    if not isinstance(source,dict):
        raise EngineeringImportError('invalid_source','source_geometry 必须是明确的来源描述。')
    allowed={'workspace_id','candidate','geometry_path','mesh_path','design_basis_path','expected_sha256','expected_mesh_sha256','expected_basis_sha256'}
    if set(source)-allowed:raise EngineeringImportError('invalid_source','source_geometry 含不支持字段。')
    if set(payload)-{'prompt','source_geometry','memory_context','domain'}:
        raise EngineeringImportError('invalid_payload','工程导入不接受教学参数或隐式仿真设置；请使用原工程来源。')
    if payload.get('domain') not in (None,'floating_platform'):
        raise EngineeringImportError('domain_mismatch','当前来源是单个浮式平台，不能作为其他模型族导入。')
    prompt=payload.get('prompt','')
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>6000:
        raise EngineeringImportError('invalid_payload','请提供 1—6000 字的工程导入描述。')
    config=_integration_settings(settings)
    workspaces=_integration_directory(config,'WORKSPACES',workspaces)
    if workspaces is None:
        raise EngineeringImportError('integration_unavailable','尚未配置工程来源目录，请联系管理员；普通可视化仍可使用。')
    profiles=_integration_profiles(config)
    workspace_id=source.get('workspace_id') or config.get(CONFIG_PREFIX+'WORKSPACE_ID')
    if not workspace_id:
        raise EngineeringImportError('integration_unavailable','请指定工程工作区，或由管理员配置默认工作区。')
    base=_workspace(workspaces,workspace_id)
    candidate=source.get('candidate')
    if candidate is None and source.get('geometry_path'):
        path=_relative_path(source['geometry_path'])
        candidate=next((k for k,v in profiles.items() if v['geometry_path']==path),None)
        if candidate is None:raise EngineeringImportError('unsupported_geometry_schema','来源尚无明确候选构型映射；不能猜测构型或单位。')
    candidate=candidate or config.get(CONFIG_PREFIX+'DEFAULT_CANDIDATE')
    if candidate not in profiles:
        raise EngineeringImportError('unsupported_candidate','请指定已配置的工程构型；不会自动猜测候选。')
    profile=profiles[candidate]
    gp=_relative_path(source.get('geometry_path',profile['geometry_path']))
    mp=_relative_path(source.get('mesh_path',profile['mesh_path']))
    if gp!=profile['geometry_path'] or mp!=profile['mesh_path']:
        raise EngineeringImportError('candidate_source_mismatch','候选编号与结构化几何来源不匹配；禁止混用候选版本。')
    basis_value=source.get('design_basis_path') or config.get(CONFIG_PREFIX+'BASIS_PATH')
    if not basis_value:
        raise EngineeringImportError('integration_unavailable','请指定设计依据文件，或由管理员配置默认来源。')
    basis_path=_relative_path(basis_value)
    report,report_src,_=_read(base,gp,'candidate_geometry_report',source.get('expected_sha256'))
    mesh,mesh_src,mesh_bytes=_read(base,mp,'exact_candidate_surface_mesh',source.get('expected_mesh_sha256'))
    basis,basis_src,_=_read(base,basis_path,'design_basis',source.get('expected_basis_sha256'))
    if (not isinstance(basis,dict) or basis.get('schema')!='LJ20-C1-design-basis/v1'
        or basis.get('units',{}).get('geometry')!='m' or basis.get('units',{}).get('body_z')!='SWL0up'):
        raise EngineeringImportError('unsupported_design_basis','设计依据单位/坐标约定不匹配。')
    if not isinstance(report,dict) or report.get('candidate')!=candidate:
        raise EngineeringImportError('candidate_source_mismatch','报告中的候选编号与请求不一致。')
    metadata=_mesh(mesh);components=_components(report,profile['kind'])
    upstream=[report_src,mesh_src,basis_src]
    release=None;review_note=''
    for path,role in [(config.get(CONFIG_PREFIX+'RELEASE_PATH'),'review_release'),
                      (config.get(CONFIG_PREFIX+'REVIEW_PATH'),'review_scope')]:
        if not path:continue
        try:
            value,provenance,_=_read(base,path,role,json_value=path.endswith('.json'))
            upstream.append(provenance)
            if role=='review_release':release=value
            else:review_note=value[:12000]
        except EngineeringImportError as exc:
            if exc.code!='source_unavailable':raise
    memory=_memory(payload.get('memory_context'),workspaces)
    missing=[
        {'id':'candidate_selection','label':'用户确认的目标候选与修订','blocking':True,'reason':'报告保留多个候选，未发现唯一全系统选定/验收构型。'},
        {'id':'site_coordinates','label':'实际场址地理坐标与坐标基准','blocking':True,'reason':str(basis.get('project',{}).get('site','未提供'))},
        {'id':'farm_turbine_coordinates','label':'实际风场机位、机组数量与布置','blocking':True,'reason':'本文件只含一个平台的构件坐标，不含风场布局。'},
        {'id':'compatible_20mw_model','label':'与该 20 MW 浮式构型匹配的气动/结构模型','blocking':True,'reason':'CAD装配与设计依据未绑定可执行全系统模型。'},
        {'id':'hydro_mooring_bindings','label':'同一候选的水动力、系泊与载荷接口','blocking':True,'reason':'需绑定已核对版本及适用范围；不得混用C14/C15。'},
        {'id':'site_environment','label':'真实场址风浪流工况','blocking':True,'reason':str(basis.get('load_scenarios',{}).get('environment_status','未知'))},
        {'id':'engineering_acceptance','label':'工程适用性与验收状态','blocking':True,'reason':'阶段报告不是工程最终批准，已有失败项继续保留。'},
    ]
    if profile['kind']=='wet_surface':missing.append({'id':'full_assembly','label':'同一候选的完整结构/塔机装配','blocking':True,'reason':'当前文件仅为水动力湿表面，不能代替全机组几何。'})
    identity={'workspace_id':workspace_id,'candidate':candidate,'source_hashes':[s['sha256'] for s in upstream]}
    ident=_hash(json.dumps(identity,sort_keys=True,separators=(',',':')).encode())[:24]
    folder=output_root/ident
    _immutable(folder/'mesh.json',mesh_bytes)
    mesh_artifact={**metadata,'schema':'ai-engineer-scene-v1','units':'m','coordinate_system':'local_cartesian',
                   'source':{'path':mesh_src['path'],'sha256':mesh_src['sha256']},
                   'cached_source':{'path':str((folder/'mesh.json').resolve()),'sha256':_hash(mesh_bytes)},'upstream_source':mesh_src,
                   'scope':profile['kind'],'not_structural_mesh':True}
    geometry={'schema':'engineering-geometry-v1','kind':'floating_platform','candidate':candidate,
        'coordinate_system':'local_cartesian','coordinate_convention':'body x/y horizontal; z up; SWL=0','units':'m',
        'workspace_id':workspace_id,'turbines':[],'components':components,'mesh':mesh_artifact,
        'upstream_sources':upstream,'source_identity':identity,'site':basis.get('project',{}).get('site'),
        'rated_power_MW':basis.get('project',{}).get('power_MW'),'environment_class':'offshore_floating',
        'scope':profile['kind'],'accepted':False,'engineering_finalized':False,'missing_inputs':missing}
    raw=json.dumps(geometry,ensure_ascii=False,sort_keys=True,allow_nan=False,indent=2).encode('utf-8')
    _immutable(folder/'geometry.json',raw)
    geometry={**geometry,'source':{'path':str((folder/'geometry.json').resolve()),'sha256':_hash(raw)}}
    scene,transform=_preview(components,mesh,candidate)
    params={'rated_power_MW':basis['project'].get('power_MW'),'design_water_depth_m':basis.get('load_scenarios',{}).get('depth_m'),
            'cavity_count':basis.get('reference',{}).get('cavities'),'steel_target_t':basis['project'].get('permanent_steel_limit_t'),
            'capex_target_CNY':basis['project'].get('capex_CNY')}
    warnings=['当前展示 '+candidate+' 候选，未认定为最终选定构型。','平台构件坐标不是风场机位；真实连江位置仍缺失。',
              '设计工况来自原报告假设，不作为当地实测极值或 OEM 认证工况。','CAD 检查通过不等于全系统工程验收通过。']
    if profile['kind']=='wet_surface':warnings.append('本候选仅导入水动力湿表面；没有补造塔架、叶轮或机舱。')
    return {'schema':'world-design-v1','id':'engineering_'+ident,'domain':'floating_platform','model_kind':'engineering_configuration',
        'title':'连江 20 MW · '+profile['label'],'prompt':prompt.strip(),'source':'wiscomper','status':'designed','accepted':False,
        'parameters':{},'parameter_metadata':{},'engineering_parameters':params,'engineering_parameter_provenance':{
            'source':basis_src,'values_are':'original_design_basis_inputs_and_targets','site_environment':'assumed_not_localextremes_orOEMDLC'},
        'objects':components,'engineering_objects':components,'engineering_geometry':geometry,'engineering_mesh':mesh_artifact,
        'scene':scene,'scene_transform':transform,'constraints':[{'id':'source_scope','description':'单个平台局部装配或湿表面，不自动构成风场。'},
             {'id':'candidate_identity','description':'候选编号与哈希共同绑定，任何后续计算必须使用相同构型。'}],
        'observables':[],'simulation':{'available':False,'reason':'工程几何尚未绑定兼容且可验证的物理模型；不得回退到教学风机ROM。'},
        'missing_inputs':missing,'warnings':warnings,'assumptions':['结构化几何是坐标唯一来源；记忆摘要仅提供上下文。',
            '预览点为真实构件体积中心或真实网格顶点采样，不是构件外形；完整外形见精确网格。'],
        'source_provenance':upstream,'memory_context':memory,
        'candidate_selection':{'selected':candidate,'status':'review_candidate_not_final','basis':'explicit_request' if source.get('candidate') or source.get('geometry_path') else 'configured_default_review_candidate',
            'candidates':[{'id':k,'label':v['label'],'scope':v['kind'],'available':(base/v['geometry_path']).is_file() and (base/v['mesh_path']).is_file()} for k,v in profiles.items()]},
        'source_checks':{'cad_report_passed':report.get('passed'),'checks':report.get('checks',[]),'limitations':report.get('limitations',[]),
            'design_basis_failure_inputs':basis.get('failure_inputs',[]),'release':release,'review_scope_excerpt':review_note[:1600]},
        'design_metadata':{'generator':'wiscomper_verified_engineering_import','routing':'explicit_source_geometry','paid_model_used':False,
            'artifact_directory':str(folder.resolve()),'geometry_role':'single_platform_local_configuration','source_files':['server/engineering_design.py','server/world_design.py'],
            'renderer':'wiscomper-engineering-mesh-v1','scene_evidence':'source_coordinates_preview_not_simulation'}}
