## Javascript part of the pipeline source code

The files in this directory are used by the python part of the pipeline source code, to statically analyze javascript files via AST parsing.





The module`collectAPIs.js` is used to detect API inside javascript files, that might or might not be relevant. Irrelevant APIs are filtered out by the python scripts that calls this module.



The module `collectNestedScripts.js` will instead detect the import of scripts. It looks for `require` and `import` statements, and filters out script imports that are are not inside the local extension directory (these are normally remote script files and we do not analyse them)