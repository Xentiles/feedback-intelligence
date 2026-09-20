/* Orbital Clarity: shared, approved fluid-sand equations. */
export const vertex = `#version 300 es
in vec2 a; void main(){ gl_Position=vec4(a,0.,1.); }`
export const fragment = `#version 300 es
precision highp float;
precision highp int;
out vec4 color;
uniform vec2 resolution;
uniform vec2 cssSize;
uniform float time;
uniform float intensity;
float hash(vec2 p){
  p=mod(p,289.);
  return fract((p.x*34.+1.)*p.x/289.+(p.y*71.+1.)*p.y/293.);
}
float noise(vec2 p){
  vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
  return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+vec2(1.,1.)),f.x),f.y);
}
float fbm(vec2 p){
  return noise(p)*.57+noise(p*2.03+17.2)*.28+noise(p*4.11+41.7)*.15;
}
// Keep the approved broad field; use an independent hash for the fine material.
float grainHash(vec2 p, uint seed){
  uvec2 q=uvec2(ivec2(p));
  uint h=(q.x*0x9e3779b9u)^(q.y*0x85ebca6bu)^seed;
  h=(h^(h>>16u))*0x7feb352du;
  h=(h^(h>>15u))*0x846ca68bu;
  h=h^(h>>16u);
  return float(h>>8u)/16777216.;
}
float grainNoise(vec2 p, uint seed){
  vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
  return mix(mix(grainHash(i,seed),grainHash(i+vec2(1.,0.),seed),f.x),
             mix(grainHash(i+vec2(0.,1.),seed),grainHash(i+vec2(1.,1.),seed),f.x),f.y);
}
void main(){
  vec2 pixel=vec2(gl_FragCoord.x/resolution.x,1.-gl_FragCoord.y/resolution.y)*cssSize;
  vec2 p=pixel/430.;
  float t=time;
  vec2 warp=vec2(fbm(p*.74+vec2(t*.028,3.4)),fbm(p*.69+vec2(8.2,-t*.022)));
  float field=p.x*.78+p.y*.67+warp.x*2.2+warp.y*.9-t*.052;
  float wave=sin(field*3.5);
  float crest=exp(-pow((wave-.55)*5.,2.));
  float broad=(fbm(p*.65+warp+vec2(t*.011,0.))-.5)*10.;
  float dunes=wave*5.5+crest*7.5+broad-3.5;
  // Grain advects smoothly with the surface. The seed does not change each frame.
  vec2 drift=vec2(sin(p.y*1.7+t*.13),cos(p.x*1.4+t*.11))*2.3;
  vec2 q=(pixel+drift)*.82;
  vec2 q2=vec2(q.x*.8-q.y*.6,q.x*.6+q.y*.8)*1.73+31.;
  vec2 q3=vec2(q.x*12./13.+q.y*5./13.,-q.x*5./13.+q.y*12./13.)*2.27+71.;
  float fine=(grainNoise(q,11u)+grainNoise(q2,137u)+grainNoise(q3,719u)-1.5)*9.;
  float value=clamp(44.+intensity*(dunes+fine),24.,60.);
  color=vec4(vec3(value/255.),1.);
}`
