## Python part of the pipeline source code





The files in this directory implement the core logic of the pipeline. 





### High level overview

Each python script receives one argument indicating what operation it should perform, and one argument that points to a valid JSON file with extension ID - versions pairs of all extensions that are to be analysed (**relative path is used**). Please remember to first setup the structure of the directories in the container as specified in the repository home page, before running the scripts. 



Below we provide a high level overview of how each script operates. Every script's main process spawns 30 processes to work on extension IDs. Each script execution will generate a resulting JSON file with the results that the script stored in the database inside the `~/results/` directory. This is for the convenience of the user, to view how the results look like. Additionally an error_log file is generated, with tolerated small errors encountered during the analysis.

Each script will first clear the respective table where it stores results in, before storing the results, to avoid errors.



- `collect_permissions.py`: can be called with two different options

  - `-parse_manifest` 

    How it works:

    - Each process will work on a separate extension ID
    - For each extension, and each version belonging to it, the manifest file is parsed
    - If the manifest could be parsed, the manifest version is collected, or if not present we assume version 2 is on use by default
    - Depending on the manifest version,  API permissions are collected and categorized (relevan/irrelevant, optional/mandatory ..) 
    - Host permissions are collected and categorized into the 5 categories described in the thesis methodology chapter
    - Results are converted to a JSON string and stored in the database table `permissions_overview`

  

  - `-detect_changes`

    How it works:

    - Each process will work on a separate extension ID
    - For each extension ID, the respective row in the table `permissions_overview` is queried from the database
    - Based on the information queried from the database, and the defined methodology in our thesis, for each extension update we compute changes in API permissions (new / deleted, moved to optional / mandatory)
      A tag describing the change in host permissions is also generated (e.g. `all_urls_added` / `url_count_decrease` / `irrelevant` etc.)
    - Information about the changes is stored in the database table `permission_changes`

  









- `static_analysis.py`: can be called with two different options

  - `-analyze` 

    How it works:

    - Each process will work on a separate extension ID
    - For each extension ID, the manifest is crawled to find links to files with code
    - the manifest entries `content_scripts`, `background` , `browser_action` -> `default_popup` and `web_accessible_resources` are inspected, and any script files or pages found are collected
    - BeautifulSoup is called on all HTML files collected, **which can be locally found inside the extension directory**. Additional script file names are collected in this step, as well as inline scripts. All of them are included by background context pages, so they will execute in the background context.
    - On every background and foreground script collected so far, call our AST parser `collectNestedScripts.js` which is inside the `js_code` directory. If the script file can be locally found in the extension repository, and our parser can parse it, all additional scripts included as well as any scripts they include are recursively added in the list of collected scripts (grouped into foreground and background context, depending on the context of the script including them)
    - The above process is repeated for each collected script, until all script files have been recursively collected. 
    - Special care is taken to keep track of the directory path. E.g. a script inside a directory might include a script inside the same directory, or might include a script in the root extension directory. In both cases we store the relevant path for each script included. We encountered cases of scripts in the root directory having the same name as scripts inside subdirectories, so our approach is error-free in these cases and works as intended.
    - Finally, having collected all possible scripts, call the javascript module `collectAPIs.js` inside the `js_code` directory on each script, to collect API usage. 
    - API calls found are separated into relevant and irrelevant, relevant here meaning that the API call is associated with some relevant permission.
    - Note down which script uses what API, and store all relevant information in JSON format in the database table `api_overview`

  - `-detect_changes`

    How it works:

    - Each process will work on a separate extension ID
    - For each extension ID, the respective table row from the database table `api_info` is collected.
    - Based on the gathered information and our methodology described in the thesis, differences in the API calls are detected between updates
    - The results are stored in the database table `api_changes`













- `merge_tables.py`: can be called with two different options

  - `-merge_overview` 

    How it works:

    - Each process will work on a separate extension ID
    - For each extension ID, the respective row is retrieved from the database table `api_overview` and the database table `permissions_overview`. If this ID does not exist in either table, no  further steps can be performed (NOTE: if the same JSON file was used as an argument for all scripts called, such cases of inconsistency between tables will not occur.)
    - The results from the two tables are combined into one
    - At this point API usage information is converted into utilized permission information, by taking into account both permissions requested as well as API calls collected.
    - A category is assigned to each version (c0 - c3+++) as described in our methodology in the thesis
    - The results are stored in the database table `overview_complete`

  - `-merge_changes`

    How it works:

    - Each process will work on a separate extension ID
    - For each extension ID, the respective row is retrieved from the database table `api_changes` and the database table `permission_changes`. If this ID does not exist in either table, no  further steps can be performed (NOTE: if the same JSON file was used as an argument for all scripts called, such cases of inconsistency between tables will not occur.)
    - The results from the two tables are combined into one, by also taking into account information in the `overview_complete` table for this ID.
    - All changes in requested and utilized permissions between updates are evaluated
    - A transition grade is assigned on each update
    - The results are stored in the database table `changes_complete`









