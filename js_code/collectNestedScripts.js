const acornLoose = require("acorn-loose");
const fs = require('fs');
const walk = require("acorn-walk");



var args = process.argv.slice(2);
var flag = true;
try {
var ast = acornLoose.parse(fs.readFileSync(args[0]).toString(), {ecmaVersion: 2020}); }
catch (e) { flag = false;}
if (args[1]) {
var prefix = args[1].toString(); }

API_calls = [];
checked_nodes = [];
last_node_checked = null;
scripts = [];

function tree_walker(ast_tree) {
  walk.fullAncestor(ast_tree, (node, _, ancestors) => {
      try {
        
          if (node.type === "CallExpression") {
            //require external script
              findRequireScript(node)
              }
          else if (node.type === "ImportExpression") {
            // import external script
            findImportScript(node)
          }
                
              
          
      } catch (e) {
          //console.error("Error in tree_walker():", e);
      }
  });
}

function findImportScript(node) {
  try {
    if (node.source) {
      path = prefix + node.source.value.toString()
      if (fs.existsSync(path)) {
      scripts.push(node.source.value); }
    }
    else {
      //console.log('no specifiers')
    } } catch (error) {}
  
}

function findRequireScript(node) {
  try {
  if (node.callee.name = "require") {
    flag = false;
    node.arguments.forEach(function(x, i) { if ((x.type == "Literal") && (x.value) && (x.value.toString().endsWith("js") ))  {
      if (fs.existsSync(prefix + x.value.toString())) {
      scripts.push(x.value);}}})
    
  } } catch (error) { } }








if (flag) {
tree_walker(ast) }
//console.log('SCRIPT ' + args[0].toString() +  '\nAPI CALLS: ' + API_calls);
final = []
//scripts.forEach(function(x,i) {if (!x.toString().endsWith(".js")) {}}})
console.log(scripts.toString())