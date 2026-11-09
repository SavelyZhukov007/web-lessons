import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const L=hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255).map(c=>c<=.04045?c/12.92:((c+.055)/1.055)**2.4).reduce((s,c,i)=>s+c*[.2126,.7152,.0722][i],0);
for(const theme of ['values','values-night']) test(`Android widget WCAG AA fallback — ${theme}`,()=>{
 const xml=readFileSync(new URL(`../../android/native/res/${theme}/itc_widget_colors.xml`,import.meta.url),'utf8');
 const colors=Object.fromEntries([...xml.matchAll(/<color name="([^"]+)">(#[0-9A-Fa-f]{6})<\/color>/g)].map(x=>[x[1],x[2]]));
 for(const [fg,bg] of [['widget_fg','widget_bg'],['widget_muted','widget_bg'],['widget_accent','widget_bg'],['widget_chip_fg','widget_chip_bg']]){
  const a=L(colors[fg]),b=L(colors[bg]),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);assert.ok(ratio>=4.5,`${fg} on ${bg}: ${ratio}`);
 }
});
