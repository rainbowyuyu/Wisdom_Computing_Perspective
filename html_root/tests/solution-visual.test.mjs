import { test } from 'node:test';
import assert from 'node:assert/strict';
import { visualMarkup } from '../static/js/solution-visual.js';

test('geometry draws independent edges without joining unrelated marked points', () => {
  const visual = {kind:'geometry', points:[[0,0],[4,0],[1,3],[2.5,1.5]], labels:['A','B','C','D'], segments:[[0,1],[1,2],[2,0],[0,3]]};
  const html = visualMarkup(visual);
  const lines = [...html.matchAll(/<polyline points="([^"]+)"/g)];
  assert.equal(lines.length, 4);
  assert.ok(lines.every(line => line[1].split(' ').length === 2));
  assert.equal(lines[0][1].split(' ')[0], lines[3][1].split(' ')[0]);
  const half = visualMarkup(visual,.5).match(/<polyline points="([^"]+)"/)[1];
  const [start,end] = lines[0][1].split(' ').map(p=>p.split(',').map(Number));
  const halfway = half.split(' ')[1].split(',').map(Number);
  assert.ok(Math.abs(halfway[0]-(start[0]+end[0])/2)<.02);
  assert.equal(halfway[1],start[1]);
  assert.equal((visualMarkup({...visual, segments:[]}).match(/<polyline/g) || []).length, 0);
  assert.equal((visualMarkup({...visual, segments:undefined}).match(/<polyline/g) || []).length, 1);
});

test('geometry retains sampled circle paths instead of replacing them with point edges',()=>{
  const circle=Array.from({length:81},(_,i)=>[3*Math.cos(i*Math.PI/40)-1,3*Math.sin(i*Math.PI/40)+1]);
  const html=visualMarkup({kind:'geometry',curves:[{label:'C',points:circle}],points:[[-1,1]],segments:[]});
  const coords=html.match(/<polyline points="([^"]+)"/)[1].split(' ').map(v=>v.split(',').map(Number));
  const width=Math.max(...coords.map(p=>p[0]))-Math.min(...coords.map(p=>p[0]));
  const height=Math.max(...coords.map(p=>p[1]))-Math.min(...coords.map(p=>p[1]));
  assert.ok(Math.abs(width-height)<.03);
});

test('number line preserves open endpoints, intersections and safe labels',()=>{
  const html=visualMarkup({kind:'number_line',rows:[
    {label:'正数',intervals:[{lower:0,upper:null,lower_closed:false}]},
    {label:'交集<script>',intervals:[{lower:3*Math.sqrt(2),upper:6,lower_closed:false,upper_closed:false,lower_label:'3√2',upper_label:'6'}]},
    {label:'无解',intervals:[]}
  ]});
  assert.equal((html.match(/data-endpoint="open"/g)||[]).length,3);
  assert.ok(html.includes('3√2') && html.includes('∅'));
  assert.ok(!html.includes('<script>'));
});
