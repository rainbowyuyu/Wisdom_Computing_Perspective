import { test } from 'node:test';
import assert from 'node:assert/strict';
import { NODES, EDGES, getNodes, getGraphDataFor3D, getMetroPathForSection, getInNeighbors, getOutNeighbors } from '../static/js/site-graph.js';

test('page station uses its ID, not the first subtool assigned to the page', () => {
    assert.equal(getMetroPathForSection('examples').find(n => n.current).id, 'examples');
    assert.equal(getMetroPathForSection('devtools', 'latex').find(n => n.current).id, 'devtools-latex');
    assert.equal(getMetroPathForSection('admin').find(n => n.current).id, 'home-admin');
    assert.deepEqual(getMetroPathForSection('missing'), []);
    assert.equal(getMetroPathForSection('home', null, 'calc-normal').find(n => n.current).id, 'home');
});

test('all graph branches are retained and selected leaves read their own edges', () => {
    const path = getMetroPathForSection('calculate');
    const expected = getOutNeighbors('calculate').map(n => n.id);
    assert.ok(expected.length > 3);
    assert.deepEqual(path.filter(n => n.relation === 'outgoing').map(n => n.id), expected);
    assert.ok(expected.includes('settings-calc'));
    const leaf = getMetroPathForSection('calculate', null, 'calc-math-input');
    assert.deepEqual(leaf.filter(n => !n.current).map(n => n.id), ['calc-normal']);
    assert.equal(leaf.find(n => n.current).id, 'calc-math-input');
});

test('ForceGraph mutation cannot corrupt canonical nodes, links or station names', () => {
    const before = getMetroPathForSection('calculate');
    const graph = getGraphDataFor3D();
    graph.links.forEach(e => { e.source = graph.nodes.find(n => n.id === e.source); e.target = graph.nodes.find(n => n.id === e.target); });
    graph.nodes.forEach(n => { n.x = 123; n.name = 'changed'; n.keywords?.push('changed'); });
    assert.deepEqual(getMetroPathForSection('calculate'), before);
    assert.equal(getNodes().some(n => n.x === 123 || n.name === 'changed' || n.keywords?.includes('changed')), false);
    assert.ok(EDGES.every(e => typeof e.source === 'string' && typeof e.target === 'string'));
});

test('graph edits appear without a second navigation list; malformed edges and cycles stay bounded', () => {
    const length = EDGES.length;
    const nodeLength = NODES.length;
    const original = getOutNeighbors('calc-normal').map(n => n.id);
    try {
        NODES.push({ id: 'new-tool', name: '新工具', section: 'calculate', type: 'subtool' });
        EDGES.push({ source: 'calc-normal', target: 'new-tool' },
            { source: { id: 'calc-normal' }, target: { id: 'new-tool' } },
            { source: 'new-tool', target: 'calc-normal' },
            { source: 'calc-normal', target: 'calc-normal' },
            { source: 'calc-normal', target: 'missing' },
            { source: 'calc-normal', target: null }, null);
        const path = getMetroPathForSection('calculate', null, 'calc-normal');
        assert.deepEqual(path.filter(n => n.relation === 'outgoing').map(n => n.id), [...original, 'new-tool']);
        assert.deepEqual(getInNeighbors('new-tool').map(n => n.id), ['calc-normal']);
        assert.equal(path.filter(n => n.current).length, 1);
        assert.deepEqual(getOutNeighbors('missing'), []);
    } finally { EDGES.length = length; NODES.length = nodeLength; }
});

test('non-actionable hubs and roles do not become page stations', () => {
    const path = getMetroPathForSection('home');
    assert.ok(path.every(n => n.section && n.type !== 'hub' && n.type !== 'role'));
});

test('every functional node is reachable; raw graph has no duplicate IDs or dangling edges', () => {
    const ids = new Set(NODES.map(n => n.id));
    assert.equal(ids.size, NODES.length);
    const edges = new Set();
    for (const edge of EDGES) {
        assert.ok(ids.has(edge.source) && ids.has(edge.target), JSON.stringify(edge));
        const key = `${edge.source}:${edge.target}`;
        assert.ok(!edges.has(key), key);edges.add(key);
    }
    const reached = new Set(['center']), pending = ['center'];
    while (pending.length) {
        for (const n of getOutNeighbors(pending.pop())) {
            if (!reached.has(n.id)) { reached.add(n.id);pending.push(n.id); }
        }
    }
    assert.deepEqual(NODES.filter(n => !reached.has(n.id)).map(n => n.id), []);
});
