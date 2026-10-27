import test from 'node:test';
import assert from 'node:assert/strict';
import {graphPath,layoutGraph} from '../web/nebula-graph.js';

test('station paths use existing links only and find a short undirected route',()=>{
  const graph={nodes:['a','b','c','d','isolated'].map(id=>({id})),links:[{source:'a',target:'b'},{source:'b',target:'c'},{source:'c',target:'d'},{source:'a',target:'d'},{source:'bad',target:'isolated'}]};
  assert.deepEqual(graphPath(graph,'a','c'),['a','b','c']);
  assert.deepEqual(graphPath(graph,'d','a'),['d','a']);
  assert.deepEqual(graphPath(graph,'a','isolated'),[]);
  assert.deepEqual(graphPath(graph,'a','a'),['a']);
  assert.deepEqual(graphPath(graph,'missing','a'),[]);
});

test('3D spring positions are deterministic and finite and leave API data untouched',()=>{
  const graph={nodes:Array.from({length:80},(_,i)=>({id:`n${i}`,kind:i<4?'hub':'formula'})),links:Array.from({length:79},(_,i)=>({source:`n${Math.floor(i/4)}`,target:`n${i+1}`}))};
  const before=JSON.stringify(graph), result=layoutGraph(graph);
  assert.equal(result.nodes.length,80);assert.equal(result.links.length,79);
  assert.equal(JSON.stringify(graph),before);assert.deepEqual(layoutGraph(graph),result);
  assert.ok(result.positions.every(p=>p.length===3 && p.every(Number.isFinite)));
  assert.ok(result.positions.some(p=>Math.abs(p[2])>10));
  assert.equal(new Set(result.positions.map(p=>p.join(','))).size,80);
});
