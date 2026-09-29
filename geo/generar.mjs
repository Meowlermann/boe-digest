import fs from 'fs';
import * as topo from 'topojson-client';
import {geoPath, geoConicConformal} from 'd3-geo';
import {presimplify, simplify, quantile} from 'topojson-simplify';
const INE = {"01":"araba-alava","02":"albacete","03":"alicante-alacant","04":"almeria","05":"avila","06":"badajoz","07":"balears-illes","08":"barcelona","09":"burgos","10":"caceres","11":"cadiz","12":"castellon-castello","13":"ciudad-real","14":"cordoba","15":"coruna-a","16":"cuenca","17":"girona","18":"granada","19":"guadalajara","20":"gipuzkoa","21":"huelva","22":"huesca","23":"jaen","24":"leon","25":"lleida","26":"rioja-la","27":"lugo","28":"madrid","29":"malaga","30":"murcia","31":"navarra","32":"ourense","33":"asturias","34":"palencia","35":"palmas-las","36":"pontevedra","37":"salamanca","38":"s-c-tenerife","39":"cantabria","40":"segovia","41":"sevilla","42":"soria","43":"tarragona","44":"teruel","45":"toledo","46":"valencia-valencia","47":"valladolid","48":"bizkaia","49":"zamora","50":"zaragoza","51":"ceuta","52":"melilla"};
const CAN = new Set(["35","38"]);
let t = JSON.parse(fs.readFileSync('package/es/provinces.json'));
if (process.env.Q) { t = presimplify(t); t = simplify(t, quantile(t, +process.env.Q)); }
const fc = topo.feature(t, t.objects.provinces);
fc.features = fc.features.filter(f=>INE[f.id]);
const pen = {type:"FeatureCollection", features: fc.features.filter(f=>!CAN.has(f.id))};
const can = {type:"FeatureCollection", features: fc.features.filter(f=>CAN.has(f.id))};
const W = 800, M = 8;
const pp = geoConicConformal().rotate([3.5,0]).parallels([36,43]).fitWidth(W-2*M, pen);
let b = geoPath(pp).bounds(pen); pp.translate([pp.translate()[0]+M-b[0][0], pp.translate()[1]+M-b[0][1]]);
b = geoPath(pp).bounds(pen);
const H = Math.ceil(b[1][1] + M);
// Canarias: recuadro abajo a la izquierda, donde el mapa deja el hueco de Portugal.
const box = [[W-M-262, H-138],[W-M, H-M]];
const pc = geoConicConformal().rotate([15.5,0]).parallels([27,29]).fitExtent([[box[0][0]+8, box[0][1]+8],[box[1][0]-8, box[1][1]-8]], can);
const r = v => Math.round(v*10)/10;
const out = {viewBox:`0 0 ${W} ${H}`, fuente:"Instituto Geográfico Nacional (CNIG), vía es-atlas 0.6.0 (MIT)", provincias:{}, centros:{},
  marco:`M${box[0][0]},${box[0][1]}H${box[1][0]}V${box[1][1]}H${box[0][0]}Z`};
for (const f of fc.features){ const s=INE[f.id]; const g=geoPath(CAN.has(f.id)?pc:pp).digits(1); out.provincias[s]=g(f); out.centros[s]=g.centroid(f).map(r); }
const ccaa = topo.feature(t, t.objects.autonomous_regions);
const mesh = topo.mesh(t, t.objects.autonomous_regions, (a,b)=>a!==b);
out.ccaa = geoPath(pp).digits(1)(mesh);
fs.writeFileSync('mapa-provincias.json', JSON.stringify(out));
console.log(out.viewBox, fs.statSync('mapa-provincias.json').size, out.centros.ceuta, out.centros.melilla, out.centros['palmas-las']);
