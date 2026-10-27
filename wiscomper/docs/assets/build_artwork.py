"""Rebuild self-contained README SVGs from the existing Wiscomper mark.

Run from any directory: python docs/assets/build_artwork.py
No network access, user content, browser, credentials or API providers required.
"""
from pathlib import Path
import xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
NS = {'s': 'http://www.w3.org/2000/svg'}
logo = ET.parse(ROOT / 'web/assets/wisdom-logo.svg').getroot()
mark = logo.find('.//s:path', NS).attrib['d']
LOGO = f'''<symbol id="wiscomper-mark" viewBox="0 0 200 200"><linearGradient id="logo-gradient" x2="1" y2="1"><stop stop-color="#66ffcc"/><stop offset=".33" stop-color="#00ccff"/><stop offset=".64" stop-color="#0000ff"/><stop offset="1" stop-color="#ff00ff"/></linearGradient><path fill="url(#logo-gradient)" fill-rule="evenodd" clip-rule="evenodd" d="{mark}"/></symbol>'''
FONT = 'font-family="Inter,Segoe UI,Microsoft YaHei,PingFang SC,Arial,sans-serif"'
DEFS = '''<linearGradient id="paper" x2="1" y2="1"><stop stop-color="#f3f1fc"/><stop offset=".5" stop-color="#f8faff"/><stop offset="1" stop-color="#eaf2fc"/></linearGradient><linearGradient id="accent" x2="1" y2="1"><stop stop-color="#4d75da"/><stop offset="1" stop-color="#9362c7"/></linearGradient><linearGradient id="glass" x2=".3" y2="1"><stop stop-color="#ffffff" stop-opacity=".95"/><stop offset="1" stop-color="#ffffff" stop-opacity=".55"/></linearGradient><filter id="shadow" x="-30%" y="-30%" width="170%" height="180%"><feDropShadow dx="0" dy="18" stdDeviation="20" flood-color="#455386" flood-opacity=".10"/></filter><pattern id="dots" width="26" height="26" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#c5cfe3" opacity=".5"/></pattern>'''


def opening(width, height, title, desc):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc"><title id="title">{title}</title><desc id="desc">{desc}</desc><defs>{DEFS}{LOGO}</defs>'''


def hero():
    parts = [opening(1600, 760, 'Wiscomper 智算视界 — Wisdom Computer Perspective',
                     'Concept illustration of the workbench: a three-dimensional fan, a formula curve and connected knowledge nodes. Product artwork, not a UI screenshot.')]
    parts.append('''<defs><linearGradient id="blade" x1=".15" x2=".85" y2="1"><stop stop-color="#c0d9ff"/><stop offset=".45" stop-color="#829de3"/><stop offset="1" stop-color="#8f76c7"/></linearGradient><linearGradient id="hub" x2="1" y2="1"><stop stop-color="#e5edfc"/><stop offset=".6" stop-color="#b1c2e8"/><stop offset="1" stop-color="#7589ba"/></linearGradient><radialGradient id="halo"><stop stop-color="#c5b6ed" stop-opacity=".45"/><stop offset="1" stop-color="#c5b6ed" stop-opacity="0"/></radialGradient></defs>
<rect width="1600" height="760" rx="30" fill="url(#paper)"/>
<circle cx="1320" cy="270" r="430" fill="url(#halo)"/><circle cx="40" cy="720" r="350" fill="#eeeaf9" opacity=".65"/>
<path d="M670 0C730 156 640 281 751 411S847 644 770 760" stroke="#fff" stroke-width="2" fill="none" opacity=".65"/>
<use xlink:href="#wiscomper-mark" x="62" y="50" width="77" height="77"/>''')
    parts.append(f'''<g {FONT}><text x="148" y="94" font-size="16" font-weight="600" letter-spacing="2.1" fill="#6c78a0">SEE · EXPLORE · CREATE</text>
<text x="78" y="245" font-size="91" letter-spacing="-4" font-weight="750" fill="url(#accent)">Wiscomper</text>
<text x="80" y="328" font-size="62" font-weight="650" letter-spacing="9" fill="#354466">智算视界</text>
<text x="84" y="374" font-size="23" letter-spacing="1" fill="#7b86a3">Wisdom Computer Perspective</text>
<text x="80" y="474" font-size="38" font-weight="550" fill="#4c557e">让想法，动起来。</text>
<text x="83" y="524" font-size="22" fill="#78849e">从文字、公式与图片，走进可探索的动态世界。</text>
<g font-size="16" font-weight="500" fill="#626c98"><rect x="82" y="579" width="146" height="45" rx="22.5" fill="#fff" stroke="#e0dff0"/><text x="105" y="608">2D + 3D</text><rect x="241" y="579" width="144" height="45" rx="22.5" fill="#fff" stroke="#e0dff0"/><text x="269" y="608">交互探索</text><rect x="398" y="579" width="144" height="45" rx="22.5" fill="#fff" stroke="#e0dff0"/><text x="427" y="608">持续迭代</text></g>
<text x="84" y="701" font-size="14" letter-spacing="1.6" fill="#96a0b5">AN INTERACTIVE VISUALIZATION WORKBENCH</text></g>''')
    parts.append('''<g filter="url(#shadow)"><rect x="831" y="145" width="687" height="452" rx="26" fill="url(#glass)" stroke="#fff" stroke-width="2"/><rect x="849" y="202" width="651" height="314" rx="17" fill="#f2f5fd"/><rect x="849" y="202" width="651" height="314" rx="17" fill="url(#dots)"/></g>''')
    parts.append(f'''<g {FONT}><circle cx="862" cy="176" r="5" fill="#a2b0cc"/><circle cx="879" cy="176" r="5" fill="#c3cde0"/><circle cx="896" cy="176" r="5" fill="#d7ddeb"/><text x="1449" y="181" font-size="12" text-anchor="end" letter-spacing="1.8" fill="#8b94ad">3D · STRUCTURAL VIEW</text></g>''')
    parts.append('''<ellipse cx="1192" cy="476" rx="157" ry="16" fill="#6a7eaf" opacity=".12"/><path d="M1168 390L1147 474Q1192 489 1239 474L1215 389" fill="url(#hub)" stroke="#aabce0" stroke-width="1.5"/><path d="M1119 474Q1192 460 1262 474L1273 487Q1190 505 1108 487Z" fill="#dbe5f8" stroke="#b7c8e9"/><g transform="translate(1184 344) rotate(-9) scale(.85 1)"><ellipse cx="18" cy="3" rx="125" ry="128" fill="#dce6f6" fill-opacity=".4" stroke="#bbcae7" stroke-width="5"/><ellipse rx="125" ry="128" fill="#f4f7fd" fill-opacity=".45" stroke="#a9bce0" stroke-width="4"/>''')
    for angle in range(0, 360, 72):
        parts.append(f'''<path transform="rotate({angle})" d="M-16,-19 C-52,-40 -49,-91 -17,-107 C15,-121 48,-106 43,-84 C39,-65 21,-27 12,-13 Z" fill="url(#blade)" stroke="#829bd1" stroke-width="1.1"/>''')
    parts.append('''<ellipse rx="29" ry="31" fill="url(#hub)" stroke="#95acd8" stroke-width="2"/><circle cx="-6" cy="-7" r="8" fill="#edf3ff" opacity=".85"/><ellipse cx="-19" cy="-1" rx="134" ry="136" fill="none" stroke="#aebee0" stroke-width="2" opacity=".6"/>''')
    for angle in (0, 30, 60, 90, 120, 150):
        parts.append(f'<path d="M-153 -1H115" transform="rotate({angle} -19 -1)" fill="none" stroke="#aabce0" stroke-width="1.2" opacity=".6"/>')
    parts.append('''</g><g stroke="#8bbbd6" fill="none" stroke-width="2.3" opacity=".65"><path d="M1329 294C1399 269 1414 298 1456 276"/><path d="M1338 332C1395 312 1414 338 1462 318"/><path d="M1335 371C1405 356 1416 383 1464 366"/><path d="M1327 410C1394 397 1424 429 1460 412"/></g><g fill="#8bbbd6" opacity=".65"><path d="M1456 276l-9-3 3 10Z"/><path d="M1462 318l-10-3 3 10Z"/><path d="M1464 366l-10-3 3 10Z"/><path d="M1460 412l-10-3 3 10Z"/></g>
<circle cx="878" cy="553" r="17" fill="url(#accent)"/><path d="M874 545L885 553 874 560Z" fill="#fff"/><path d="M917 553H1320" stroke="#e3e8f4" stroke-width="5" stroke-linecap="round"/><path d="M917 553H1114" stroke="#8c8bd1" stroke-width="5" stroke-linecap="round"/><circle cx="1114" cy="553" r="7" fill="#fff" stroke="#7776c5" stroke-width="3"/>''')
    parts.append(f'<g {FONT} font-size="13" fill="#8b96af"><text x="1357" y="558">00:12 / 00:20</text></g>')
    parts.append('''<g filter="url(#shadow)"><rect x="765" y="58" width="303" height="159" rx="22" fill="url(#glass)" stroke="#fff" stroke-width="2"/></g>
<g stroke="#d4dcec" stroke-width="1.2"><path d="M798 182H1041M823 91V192"/><path d="M798 137H1041" stroke-dasharray="3 7"/></g><path d="M801 177Q842 180 867 146T932 129T1039 95" fill="none" stroke="url(#accent)" stroke-width="3.5" stroke-linecap="round"/><circle cx="932" cy="129" r="5.5" fill="#fff" stroke="#8a75c7" stroke-width="2.5"/>''')
    parts.append(f'<g {FONT}><text x="796" y="88" font-size="13" letter-spacing="1.6" fill="#9b96b2">FORMULA → MOTION</text><text x="880" y="188" font-size="23" font-style="italic" font-family="Georgia,serif" fill="#6d72a4">y = f(x)</text></g>')
    parts.append('''<g filter="url(#shadow)"><rect x="1241" y="585" width="310" height="133" rx="21" fill="url(#glass)" stroke="#fff" stroke-width="2"/></g><path d="M1271 665L1310 625 1362 658 1404 620 1460 662 1522 631M1271 665L1300 697 1362 658 1404 696 1460 662 1510 693M1310 625L1404 620M1404 696L1510 693" stroke="#b9bfdf" stroke-width="1.4" fill="none"/>''')
    for i, (x, y) in enumerate([(1271,665),(1310,625),(1362,658),(1404,620),(1460,662),(1522,631),(1300,697),(1404,696),(1510,693)]):
        color = ['#8e8ad0','#7d9acb','#a391ca'][i % 3]
        radius = 7 if i in (2, 4) else 4
        parts.append(f'<circle cx="{x}" cy="{y}" r="{radius+5}" fill="{color}" opacity=".08"/><circle cx="{x}" cy="{y}" r="{radius}" fill="{color}" stroke="#fff" stroke-width="1.5"/>')
    parts.append(f'<g {FONT}><text x="858" y="660" font-size="16" fill="#8d96ae">Observe a structure.</text><text x="858" y="690" font-size="16" fill="#8d96ae">Change a parameter. See the connection.</text></g></svg>')
    return ''.join(parts)


def flow():
    parts = [opening(1600, 650, 'From an idea to an interactive explanation / 从想法到可探索的解释',
                     'Text, formulas, images and sketches enter bounded tool selection: Canvas 2D, Three.js, Manim and trusted numerical recipes. Users explore parameters, revise projects, and export scenes or video when render dependencies are installed.')]
    parts.append('<rect width="1600" height="650" rx="30" fill="url(#paper)"/>')
    parts.append(f'<g {FONT}><text x="61" y="78" font-size="35" font-weight="650" fill="#354466">从一个想法，到可以探索的解释</text><text x="63" y="113" font-size="18" letter-spacing=".3" fill="#8792ac">From an idea to an interactive explanation</text></g>')
    for x, width in [(56,336),(443,659),(1153,391)]:
        parts.append(f'<rect x="{x}" y="164" width="{width}" height="376" rx="22" fill="url(#glass)" stroke="#fff" stroke-width="2"/>')
    parts.append(f'''<g {FONT}><text x="80" y="206" font-size="15" fill="#8995b3" letter-spacing="1.2">01 / INPUT</text><text x="468" y="206" font-size="15" fill="#8995b3" letter-spacing="1.2">02 / CHOOSE &amp; VALIDATE</text><text x="1178" y="206" font-size="15" fill="#8995b3" letter-spacing="1.2">03 / EXPLORE</text></g>''')
    for i, (cn, en, icon) in enumerate([('文字描述','Text','Aa'),('数学公式','Formula','ƒ'),('图片素材','Image','▧'),('手绘草图','Sketch','⌁')]):
        y = 231 + i * 70
        parts.append(f'''<rect x="79" y="{y}" width="290" height="57" rx="13" fill="#f2f4fc"/><g {FONT}><text x="100" y="{y+36}" font-size="25" fill="#7a87bc">{icon}</text><text x="149" y="{y+25}" font-size="17" font-weight="550" fill="#566689">{cn}</text><text x="149" y="{y+46}" font-size="13" fill="#9099b0">{en}</text></g>''')
    for x in (407,1117):
        parts.append(f'<path d="M{x} 351h19m-7-7 7 7-7 7" fill="none" stroke="#a9acd0" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>')
    cards = [(468,233,'Canvas 2D','二维画布','流程 · 图片标注 · 曲线','#5c87c6'),
             (783,233,'Three.js','三维场景','构件 · 空间关系 · 运动','#7a73c0'),
             (468,375,'Manim','公式与几何','公式变形 · 二维视频','#9374bb'),
             (783,375,'Trusted recipes','数值构建','条件明确的参数实验','#5f96a8')]
    for x, y, title, cn, desc, color in cards:
        parts.append(f'<rect x="{x}" y="{y}" width="292" height="123" rx="15" fill="#f5f5fc" stroke="#e5e7f3"/><rect x="{x}" y="{y+20}" width="3" height="39" rx="1.5" fill="{color}"/><g {FONT}><text x="{x+21}" y="{y+32}" font-size="21" font-weight="600" fill="{color}">{title}</text><text x="{x+22}" y="{y+62}" font-size="17" fill="#596987">{cn}</text><text x="{x+22}" y="{y+93}" font-size="14" fill="#919ab1">{desc}</text></g>')
    outputs = [('Interact','观察与交互','播放、视角与有边界的参数'),('Revise','同一项目，继续修改','保存变化，回看历史版本'),('Export','留下作品','Scene JSON / MP4¹')]
    for i, (title, cn, desc) in enumerate(outputs):
        y = 236 + i * 90
        parts.append(f'<circle cx="1193" cy="{y+20}" r="17" fill="#efedf9"/><text x="1193" y="{y+25}" text-anchor="middle" {FONT} font-size="13" fill="#8983b5">0{i+1}</text><g {FONT}><text x="1226" y="{y+15}" font-size="20" font-weight="600" fill="#64729b">{title}</text><text x="1226" y="{y+43}" font-size="17" fill="#62728d">{cn}</text><text x="1226" y="{y+67}" font-size="13" fill="#8d99af">{desc}</text></g>')
    parts.append(f'''<g {FONT}><text x="63" y="581" font-size="14" fill="#8691aa">通用场景用于解释关系；数值方案明确模型与假设。¹ 视频导出需安装对应渲染环境。</text><text x="63" y="609" font-size="13" fill="#9ca5ba">Generic scenes explain relationships. Numerical recipes state their assumptions. Video export requires the corresponding render tools.</text></g></svg>''')
    return ''.join(parts)


if __name__ == '__main__':
    for name, content in [('wiscomper-hero.svg', hero()), ('visualization-flow.svg', flow())]:
        tree = ET.fromstring(content)
        assert not any(e.tag.split('}')[-1] in {'script', 'foreignObject', 'image'} for e in tree.iter())
        (OUT / name).write_text(content, encoding='utf-8')
        print(f'{name}: {len(content.encode())} bytes')
