const acornLoose = require("acorn-loose");
const fs = require('fs');
const walk = require("acorn-walk");


var flag = true;
API_calls = [];
var args = process.argv.slice(2);
try {
var ast = acornLoose.parse(fs.readFileSync(args[0]).toString(), {ecmaVersion: 2020}); }
catch (e) { flag = false;}


checked_nodes = [];
last_node_checked = null;

function tree_walker(ast_tree) {
    walk.fullAncestor(ast_tree, (node, _, ancestors) => {
        try {
            if (node.type === "CallExpression") {
                search_APIs(node.callee, ancestors);
            } else if (node.type === "MemberExpression") {
                search_APIs(node, ancestors)
            }



        } catch (e) {
            //console.error("Error in tree_walker():", e);
        }
    });
}


function search_APIs(node, ancestors) {
    try {
        switch (node.type) {
            case 'MemberExpression':
                if (node.object.type == 'Identifier' && node.object.name == 'chrome' && !(checked_nodes.includes(node))) { //chrome.API call found
                    checked_nodes.push(node)
                    ln = ancestors.length;
                    tmp = node.property.name;
                    for (let i = ancestors.length - 2; i > 1; i--) {
                        if (ancestors[i].type == "MemberExpression") {
                            tmp += '.' + ancestors[i].property.name
                        } else {
                            break;
                        }
                    }
                    if (!(API_calls.includes(tmp))) {
                        API_calls.push(tmp);
                    }

                } else if (node.object.type == 'Identifier' && node.object.name == 'document' && !(checked_nodes.includes(node))) {
                    if ((node.property.type == 'Identifier') && (node.property.name == 'execCommand')) {
                        checked_nodes.push(node)
                        t = ancestors[ancestors.length - 2].arguments[0]
                        if (t.type == 'Literal') {
                            if (t.value == 'paste') {
                                c = 'document.execCommand(paste)'
                                if (!(API_calls.includes(c))) {
                                  API_calls.push(c);
                              }
                            } else if (t.value == 'copy') {
                                c = 'document.execCommand(copy)'
                                if (!(API_calls.includes(c))) {
                                  API_calls.push(c);
                              }
                            } else if (t.value == 'cut') {
                                c = 'document.execCommand(cut)'
                                if (!(API_calls.includes(c))) {
                                  API_calls.push(c);
                              }
                            }

                        }

                    }
                } else if (node.object.type == 'Identifier' && node.object.name == 'navigator' && !(checked_nodes.includes(node))) {
                    if ((node.property.type == 'Identifier') && (node.property.name == 'geolocation')) {
                      tmp = 'navigator.geolocation.' + ancestors[ancestors.length - 2].property.name;
                      if (!(API_calls.includes(tmp))) {
                        API_calls.push(tmp);
                    }
                    }
                } else if (!(checked_nodes.includes(node))) { //dive inside nested member expressions and look for chrome.API calls
                    ancestors.push(node.object);
                    checked_nodes.push(node);
                    search_APIs(node.object, ancestors);
                }
                break;
            default:
        }
    } catch (error) {
        //console.log('error working on AST')
    }

}

if (flag) {
tree_walker(ast) }
//console.log('SCRIPT ' + args[0].toString() +  '\nAPI CALLS: ' + API_calls);
console.log(API_calls.toString())