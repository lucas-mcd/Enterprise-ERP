import ts from 'typescript';
import {readdirSync,readFileSync} from 'node:fs';
import {join} from 'node:path';
function scan(dir){return readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?scan(join(dir,e.name)):/\.tsx?$/.test(e.name)&&!e.name.includes('.test.')?[join(dir,e.name)]:[]);}
const calls=[];
for(const file of scan('src')){
 const source=ts.createSourceFile(file,readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true);
 function visit(node){
  if(ts.isCallExpression(node)&&['request','download','authenticatedFetch','fetch'].includes(node.expression.getText(source)))calls.push({file,line:source.getLineAndCharacterOfPosition(node.getStart()).line+1,client:node.expression.getText(source),path:node.arguments[0]?.getText(source),options:node.arguments[1]?.getText(source)});
  ts.forEachChild(node,visit);
 }visit(source);
}
console.log(JSON.stringify(calls,null,2));
