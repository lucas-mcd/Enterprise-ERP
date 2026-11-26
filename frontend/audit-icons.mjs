import ts from 'typescript';
import * as icons from 'lucide-react';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
function scan(dir) {
  return readdirSync(dir, {withFileTypes:true}).flatMap(e => e.isDirectory() ? scan(join(dir,e.name)) : /\.tsx?$/.test(e.name) ? [join(dir,e.name)] : []);
}
let count=0;
for(const file of scan('src')) {
 const source=ts.createSourceFile(file, readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true);
 for(const item of source.statements) {
  if(!ts.isImportDeclaration(item) || item.moduleSpecifier.text!=='lucide-react')continue;
  const bindings=item.importClause?.namedBindings;
  if(bindings && ts.isNamedImports(bindings))for(const entry of bindings.elements){
   const name=(entry.propertyName??entry.name).text;
   if(!entry.isTypeOnly && !item.importClause.isTypeOnly && !(name in icons))throw new Error(`${file}: missing icon ${name}`);
   count++;
  }
 }
}
console.log(`Validated ${count} lucide-react named imports across all frontend sources.`);
