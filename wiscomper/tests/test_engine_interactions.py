"""Exercise real pointer/touch input and deterministic declarative scene state."""
import math
import os

import pytest

from server.interactions import bake_scene, validate_exploration
from server.schema import Scene
from test_engine_mechanical import open_scene

pytestmark = pytest.mark.skipif(os.getenv('RUN_REAL_EXPORT') != '1', reason='Requires a real headless browser.')


def exploration_scene(mode='3d'):
    objects = ([
        {'id': 'part', 'kind': 'box', 'parent_id': 'joint', 'x': 1, 'width': 1, 'height': 1, 'depth': 1},
        {'id': 'joint', 'kind': 'group', 'x': -1, 'rotation': math.pi / 2},
        {'id': 'fixed', 'kind': 'box', 'x': 3, 'width': 1, 'height': 1, 'depth': 1},
    ] if mode == '3d' else [
        {'id': 'part', 'kind': 'rect', 'width': 2, 'height': 2},
        {'id': 'fixed', 'kind': 'rect', 'x': 4, 'width': 1, 'height': 1},
    ])
    scene = Scene.model_validate({'title': 'Exploration', 'mode': mode, 'duration': 6,
        'camera': {'azimuth': 0, 'elevation': 0, 'distance': 12, 'orbit': .4}, 'objects': objects}).model_dump()
    target = 'joint' if mode == '3d' else 'part'
    scene['interactions'] = [
        {'id': 'travel', 'label': 'Travel', 'value': 0, 'min': -1, 'max': 2, 'step': .1, 'kind': 'slider', 'description': 'Bounded assembly travel', 'unit': '',
         'bindings': [{'target_id': target, 'property': 'x', 'multiplier': 1}],
         'drag': {'target_id': target, 'axis': 'horizontal' if mode == '3d' else 'vertical', 'sensitivity': .01}},
        {'id': 'offset', 'label': 'Offset', 'value': 0, 'min': -1, 'max': 1, 'step': .1, 'kind': 'slider', 'description': 'Additional local offset', 'unit': '',
         'bindings': [{'target_id': target, 'property': 'x', 'multiplier': .5}]},
    ]
    return scene


def capture_events(page):
    page.evaluate('''() => {
      window.userEvents=[]; const p=window.scenePlayer;
      for (const type of ['scene-view','scene-interaction']) p.host.addEventListener(type,e=>window.userEvents.push({type,...e.detail}));
      window.sourceSnapshot=JSON.stringify(p.scene);
    }''')


def point_on(page, object_id):
    return page.evaluate('''id => {
      const p=window.scenePlayer, v=p.meshes.get(id).getWorldPosition(new p.T.Vector3()).project(p.camera), r=p.surface.getBoundingClientRect();
      return [r.left+(v.x+1)*r.width/2,r.top+(1-v.y)*r.height/2];
    }''', object_id)


def test_mouse_orbit_wheel_reset_and_absolute_preview(tmp_path):
    with open_scene(exploration_scene()) as (page, errors):
        capture_events(page)
        page.evaluate('window.renderFrame(2)')
        before = page.screenshot()
        initial = page.evaluate('window.scenePlayer.camera.position.toArray()')
        assert page.evaluate('window.scenePlayer.manipulationMode') == 'observe'
        page.mouse.move(640, 360); page.mouse.down(); page.mouse.move(780, 410, steps=5); page.mouse.up()
        camera = page.evaluate('window.scenePlayer.getView()')
        assert camera['orbit'] == 0 and camera['azimuth'] != 0
        assert page.evaluate('window.scenePlayer.camera.position.toArray()') != initial
        assert page.evaluate('window.scenePlayer.selected') is None
        assert page.evaluate('window.userEvents.at(-1).committed') is True
        assert page.evaluate('window.userEvents.some(e=>e.committed===false)')
        page.mouse.wheel(0, 180)
        page.wait_for_function('window.userEvents.at(-1).committed')
        assert page.evaluate('window.scenePlayer.getView().distance') > camera['distance']
        page.evaluate('''() => {const p=window.scenePlayer; p.setInteractionValues({travel:1,offset:.4});p.seek(4);p.seek(2)}''')
        changed = page.screenshot(path=str(tmp_path/'interactive-view.png'))
        page.evaluate('window.scenePlayer.seek(5);window.scenePlayer.seek(2)')
        assert page.screenshot() == changed
        event_count = page.evaluate('window.userEvents.length')
        page.evaluate('window.scenePlayer.resetExploration()')
        assert page.evaluate('window.scenePlayer.getView()') is None
        assert page.evaluate('window.scenePlayer.getInteractionValues()') == {'travel': 0, 'offset': 0}
        assert page.screenshot() == before
        assert page.evaluate('window.userEvents.length') == event_count
        assert page.evaluate('JSON.stringify(window.scenePlayer.scene)===window.sourceSnapshot')
        assert not errors


def test_declared_group_drag_selects_child_and_preserves_fixed_geometry():
    with open_scene(exploration_scene()) as (page, errors):
        capture_events(page)
        page.evaluate('window.scenePlayer.setManipulationMode("interact")')
        before = page.evaluate('window.scenePlayer.meshes.get("fixed").matrixWorld.elements.slice()')
        x, y = point_on(page, 'part')
        page.mouse.move(x, y); page.mouse.down(); page.mouse.move(x + 73, y, steps=4); page.mouse.up()
        assert page.evaluate('window.scenePlayer.getInteractionValues().travel') == .7
        assert page.evaluate('window.scenePlayer.selected') == 'part'
        assert page.evaluate('window.scenePlayer.getView()') is None
        assert page.evaluate('window.scenePlayer.meshes.get("part").getWorldPosition(new window.scenePlayer.T.Vector3()).toArray()') == pytest.approx([-.3, 1, 0])
        assert page.evaluate('window.scenePlayer.meshes.get("fixed").matrixWorld.elements.slice()') == before
        assert page.evaluate('window.userEvents.at(-1)') == {'type': 'scene-interaction', 'values': {'travel': .7, 'offset': 0}, 'committed': True}
        # A large pointer movement is captured and reaches the declared bound.
        x, y = point_on(page, 'part')
        page.mouse.move(x, y); page.mouse.down(); page.mouse.move(1400, y, steps=3); page.mouse.up()
        assert page.evaluate('window.scenePlayer.getInteractionValues().travel') == 2
        # An ordinary solid has selection only, with no invented movement freedom.
        x, y = point_on(page, 'fixed')
        count = page.evaluate('window.userEvents.length')
        page.mouse.move(x, y); page.mouse.down(); page.mouse.move(x - 80, y, steps=3); page.mouse.up()
        assert page.evaluate('window.userEvents.length') == count
        assert page.evaluate('window.scenePlayer.getView()') is None
        page.evaluate('window.scenePlayer.setVisible("joint",false)')
        assert page.evaluate('window.scenePlayer.meshes.get("part").userData.effectiveVisible') is False
        assert page.evaluate('JSON.stringify(window.scenePlayer.scene)===window.sourceSnapshot')
        assert not errors


def test_touch_pinch_zoom_and_pending_input_cleanup():
    with open_scene(exploration_scene()) as (page, errors):
        capture_events(page)
        cdp = page.context.new_cdp_session(page)
        points = lambda gap: [{'x': 640-gap/2, 'y': 360, 'id': 1}, {'x': 640+gap/2, 'y': 360, 'id': 2}]
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': points(160)})
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': points(320)})
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
        camera = page.evaluate('window.scenePlayer.getView()')
        assert camera['distance'] == pytest.approx(6)
        assert camera['orbit'] == 0
        assert page.evaluate('window.userEvents.at(-1).committed') is True
        assert page.evaluate('window.scenePlayer.pointers.size') == 0
        # A pending debounced wheel must not write into a replacement scene.
        page.mouse.move(640, 360); page.mouse.wheel(0, 80)
        page.wait_for_function('window.userEvents.at(-1).committed===false')
        page.evaluate('''async () => { await window.scenePlayer.load(window.scenePlayer.scene); window.eventsAfterLoad=window.userEvents.length; }''')
        page.wait_for_timeout(200)
        assert page.evaluate('window.userEvents.length===window.eventsAfterLoad')
        assert page.evaluate('window.scenePlayer.getView()') is None
        page.evaluate('window.scenePlayer.dispose()')
        assert page.evaluate('window.scenePlayer.pointers.size') == 0
        assert not errors


def test_2d_vertical_drag_pauses_and_programmatic_changes_emit_no_user_events():
    with open_scene(exploration_scene('2d')) as (page, errors):
        capture_events(page)
        assert page.evaluate('window.scenePlayer.manipulationMode') == 'interact'
        page.evaluate('window.scenePlayer.play()')
        page.mouse.move(640, 360); page.mouse.down(); page.mouse.move(640, 300, steps=4); page.mouse.up()
        assert page.evaluate('window.scenePlayer.getInteractionValues().travel') == .6
        assert page.evaluate('window.scenePlayer.playing') is False
        assert page.evaluate('window.scenePlayer.states.get("part").x') == pytest.approx(.6)
        count = page.evaluate('window.userEvents.length')
        page.evaluate('window.scenePlayer.setInteractionValues({travel:9,offset:1,unknown:7});window.scenePlayer.setView({distance:9})')
        assert page.evaluate('window.scenePlayer.states.get("part").x') == pytest.approx(2.5)
        assert page.evaluate('window.scenePlayer.getView()') is None
        assert page.evaluate('window.userEvents.length') == count
        assert page.evaluate('JSON.stringify(window.scenePlayer.scene)===window.sourceSnapshot')
        assert not errors


@pytest.mark.parametrize('mode', ['2d', '3d'])
def test_baked_export_matches_live_clipping_crossings_and_combined_controls(mode, tmp_path):
    """Sparse tracks and summed offsets must render identically on both renderers."""
    solid = 'box' if mode == '3d' else 'rect'
    objects = [
        {'id': 'alpha-high', 'kind': solid, 'x': -3, 'y': 2, 'width': 2, 'height': 1.5, 'depth': .5, 'opacity': .125,
         'frames': [{'t': 1, 'opacity': .25}, {'t': 5, 'opacity': .75, 'rotation': .2}, {'t': 6, 'opacity': .25}]},
        {'id': 'alpha-low', 'kind': solid, 'x': 3, 'y': 2, 'width': 2, 'height': 1.5, 'depth': .5, 'opacity': .875,
         'frames': [{'t': 1, 'opacity': .25}, {'t': 5, 'opacity': .75, 'rotation': -.2}, {'t': 6, 'opacity': .25}]},
        {'id': 'scale-high', 'kind': solid, 'x': -3, 'y': -2, 'width': .1, 'height': .1, 'depth': .1, 'scale': 8,
         'frames': [{'t': 1, 'scale': 12}, {'t': 5, 'scale': 20, 'rotation': .4}, {'t': 6, 'scale': 4}]},
        {'id': 'scale-low', 'kind': solid, 'x': 3, 'y': -2, 'width': .8, 'height': .8, 'depth': .8, 'scale': 2,
         'frames': [{'t': 1, 'scale': 1}, {'t': 5, 'scale': 3, 'rotation': -.4}, {'t': 6, 'scale': 1}]},
    ]
    def bindings(a, b, c, d):
        return [{'target_id': target, 'property': prop, 'multiplier': multiplier}
                for target, prop, multiplier in [('alpha-high', 'opacity', a), ('alpha-low', 'opacity', b),
                                                ('scale-high', 'scale', c), ('scale-low', 'scale', d)]]
    # Opposing contributions deliberately detect clipping each binding before summing.
    scene = Scene.model_validate({'title': 'Clipping export equivalence', 'mode': mode, 'duration': 6, 'objects': objects,
        'interactions': [
            {'id': 'primary', 'label': 'Primary', 'value': 0, 'min': 0, 'max': 1, 'step': .1, 'bindings': bindings(1, -1, 8, -4)},
            {'id': 'secondary', 'label': 'Secondary', 'value': 0, 'min': 0, 'max': 1, 'step': .1, 'bindings': bindings(-.5, .5, -4, 2)},
        ]})
    camera = {'azimuth': .3, 'elevation': .15, 'distance': 15, 'orbit': 0} if mode == '3d' else None
    exploration = {'values': {'primary': 1, 'secondary': 1}, 'camera': camera}
    original = scene.model_dump()
    baked = bake_scene(scene, exploration).model_dump()
    assert scene.model_dump() == original and baked['interactions'] == []
    assert all(len(obj['frames']) > 3 for obj in baked['objects'])
    if camera: assert baked['camera'] == camera
    original_times = {0, 1, 5, 6}
    crossings = {f['t'] for obj in baked['objects'] for f in obj['frames']} - original_times
    assert any(abs(t - 3.02) < 1e-10 for t in crossings)  # scale lower bound is .01, not zero.
    times = sorted({0, .5, 1, 2, 4, 5, 6} | {t + offset for t in crossings for offset in [-.001, 0, .001]})
    with open_scene(original) as (page, errors):
        page.evaluate('(s)=>{window.scenePlayer.setInteractionValues(s.values);window.scenePlayer.setView(s.camera)}', exploration)
        live = []
        for t in times:
            page.evaluate('window.renderFrame', t)
            live.append((page.evaluate('Object.fromEntries(window.scenePlayer.states)'), page.screenshot()))
        assert page.evaluate('window.scenePlayer.scene') == original
        page.evaluate('(scene)=>window.scenePlayer.load(scene)', baked)
        for index, t in enumerate(times):
            page.evaluate('window.renderFrame', t)
            actual = page.evaluate('Object.fromEntries(window.scenePlayer.states)')
            expected, screenshot = live[index]
            for ident in expected:
                assert actual[ident] == pytest.approx(expected[ident], abs=1e-10), (mode, t, ident)
            assert page.screenshot() == screenshot, (mode, t)
        page.screenshot(path=str(tmp_path / f'{mode}-baked-equivalence.png'))
        assert not errors


def test_toggle_rejects_fractional_value_in_live_player_and_server():
    scene = Scene.model_validate({'title': 'Visibility toggle', 'duration': 6, 'objects': [{'id': 'part', 'kind': 'rect'}],
        'interactions': [{'id': 'visible', 'label': 'Visible', 'kind': 'toggle', 'value': 1, 'min': 0, 'max': 1, 'step': 1,
                          'bindings': [{'target_id': 'part', 'property': 'opacity', 'multiplier': 1}]}]})
    for value in [.5, -1, 2]:
        with pytest.raises(ValueError): validate_exploration(scene, {'values': {'visible': value}})
    with open_scene(scene.model_dump()) as (page, errors):
        baseline = page.screenshot()
        for value in [.5, -1, 2]:
            page.evaluate('(v)=>window.scenePlayer.setInteractionValues({visible:v})', value)
            assert page.evaluate('window.scenePlayer.getInteractionValues()') == {'visible': 1}
            assert page.screenshot() == baseline
        page.evaluate('window.scenePlayer.setInteractionValues({visible:0})')
        assert page.evaluate('window.scenePlayer.states.get("part").opacity') == 0
        page.evaluate('window.scenePlayer.setInteractionValues({visible:1})')
        assert page.screenshot() == baseline
        assert not errors
