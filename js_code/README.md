## Javascript part of the pipeline source code

The files in this directory are used by the python part of the pipeline source code, to statically analyze javascript files via AST parsing.





The module`collectAPIs.js` is used to detect API inside the provided javascript file, that might or might not be relevant. Irrelevant APIs are filtered out by the python scripts that calls this module.



The module `collectNestedScripts.js` will instead look for scripts being imported via statements inside the provided javascript file. It looks for `require` and `import` statements, and only prints the imported scripts found if the imported script is located inside the extension directory. This filters out script imports that are not local files, and reduces the work load on the python scripts of having to differentiate local and not local scripts being imported.