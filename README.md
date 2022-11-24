## Pipeline for the static analysis of chrome extensions



### 1. Introduction

The files in this repository contain the source code of the pipeline that I developed for my Thesis with title "You have changed: Temporal Analysis of the Security of Browser Extension Updates".

The pipeline consists of three python files and two javascript files. The python files are found inside the python_code directory, and the javascript files inside the js_code directory. Additionally in the js_code directory the node modules required for the scripts to operate can be found.

To analyze extensions, the user must execute the python files.  If all database tables are empty, the scripts need to be called in a specific order. All python scripts have the following command line execution structure:

`python3 script_name -operation name_of_file`

The `name_of_file` part is the path to a valid JSON file, which contains extension ID and version names in a key - value pair manner.







### 2. Database Overview

There are certain tables in the database inside which the results of the analysis are stored. Some python scripts directly analyze extensions and store results inside the database, while others only make use of already existing results in the database to create the final results.

We provide an overview of the database tables.



#### Overview  tables

The following two tables provide a general overview on permissions requested and APIs used respectively, for each extension.





- Table `permissions_overview` has the following columns:

  - **id**: contains the extension id
  - **info**: contains information for each version of a specific id, in JSON format. Information includes the following:
    - could the version be analysed 
    -  what manifest version is it using 
    - list of API and host permissions requested
    - are permissions split into optional and mandatory or not

  

- Table `api_overview` has the following columns:

  - **id**: contains the extension id
  - **info**: contains information for each version of a specific id, in JSON format. Information includes the following:
    - could the version be analysed 
    - what APIs is each script using (out of all background scripts and out of all content scripts that could be found)















#### Tables about changes

The following two tables contain information about changes between extension updates. Only extension IDs which contain at least two analysable versions will appear in this table, because detecting changes for an extension update requires at least two analysable versions as reference.





- Table `permissions_changes` has the following columns:
  - **id**: contains the extension ID
  - **permission_info**: contains information in JSON format, for each update of a specific ID **which introduces a change in requested permissions**.
    Info about updates that introduce no change in requested permissions is not stored here. Information stored for each update includes the following:
    - specific changes in requested API and host permissions that this update introduces
    - name of the last update that introduced changes in requested permissions before this one (useful to keep track of the order)
  - **total_versions**: contains the count of total extension versions for this ID
  - **valid_versions**: contains the count of the total extension versions for this ID that could be analysed
  - **permission_change_updates**: contains the count of updates that introduced a change in requested permissions
- Table `api_changes` contains the following columns:
  - **id:** contains the extension ID
  - **api_info**: contains information in JSON format, for each update of a specific ID **which introduces a change in the API usage (relevant APIs only)**. Info about updates that introduce no change in API usage is not stored here. Information stored for each update includes the following:
  - specific changes in APIs used that this update introduces
    - name of the last update that introduced changes in requested permissions before this one (useful to keep track of the order)
  - **total_versions**: contains the count of total extension versions for this ID
  - **valid_versions**: contains the count of the total extension versions for this ID that could be analysed
  - **api_change_updates**: contains the count of updates, that were analysable and introduced a change in API usage







#### Merged tables

The following two tables contain combined information from previous tables. These tables are the final result of the pipeline. Information regarding update trends and privileges can be directly computed from the data contained in these two tables.





- Table `overview_complete` contains combined information from `permissions_overview` and `api_overview`. 

  Contains the following columns:

  - **id**: contains the extension ID
  - **info**: contains information for each version of this ID in JSON:
    - requested permissions, utilized permissions, manifest version, permissions split or not ..
    - over-privileged flag
    - security category (c0 - c3++)

  

  

- Table `changes_complete` contains combined information from `api_changes` and `permission_changes`. 

  Contains the following columns:

  - **id**: contains the extension ID

  - **info**: contains information in JSON format for each update **that introduced a changed either in requested or utilized permissions**. 

    Information includes:

    - requested permissions, utilized permissions
    - changes introduced such as new requested / utilized permissions, no longer requested / utilized permissions, host permission change tag ..
    - transition grade (0 - 6)
    - name of last update that introduced a change in either requested or utilized permissions (useful to keep track of the order)

  - **total_versions**: contains the count of total extension versions for this ID

  - **valid_versions**: contains the count of the total extension versions for this ID that could be analysed

  - **r_change_updates**: contains the count of updates that introduced a change in requested permissions only

  - **u_change_updates**: contains the count of updates that introduced a change in utilized permissions only

  - **r_and_u_change_updates**: contains the count of updates that introduced a change in both requested and utilized permissions







### 3. Read before running

The pipeline is run by executing each script sequentially. Because paths to extensions and paths to javascript files are hardcoded inside the pipeline files, the user must make sure that everything is setup as described in the instructions below before running the pipeline.



**BEFORE RUNNING THE PIPELINE, MAKE SURE THE FOLLOWING CONDITIONS ARE TRUE**:

- the directory python_code is located inside the home directory of the container
- the directory js_code is also located inside the home directory of the container
- the directory ~/extensions/unziped/ exists
- the directory results is located inside the home directory of the container. Inside it the results in JSON will be dumped for the convenience of the user
- Directories for all IDs and versions have been created and exist inside ~/extensions/unziped/ with the name id_version
  - e.g. for extension with id abcdef and version 1_0, the directory ~/extensions/unziped/abcdef_1_0/ must exist
- The manifest of each extension version must be already extracted and located inside the respective ID_version directory
  - The pipeline acknowledges any directory with no manifest inside as an inability to extract the manifest from the zip file, and marks the version as not analysable



We maintain the set of all extensions with regular names, inside the file **regular_names.json**. For each ID, all of it's versions are sorted in a chronological order. This is the dataset that we used for our study, as mentioned in the thesis.
In total there are 226.221 extensions, because we have removed four extension IDs which had regular naming conventions but very large Javascript files that would cause our AST parser to stall (with them the set would have been 226.225 IDs).

All of the requirement process described above is already setup on the container. We have already created a directory for each id_version combination **for all extensions in the regular_names.json** dataset,  and have put the manifest of each version inside, whenever it could be extracted. Every time the pipeline runs, all additional extension files are extracted,  analysed and then deleted, with the exception of the manifest. The manifest is not deleted whenever the pipeline finishes processing a version, but is instead left inside the id_version directory for each id and version.

We designed the pipeline this way so that additional executions of the pipeline do not need to create all these directories from the beginning and put the manifests inside them each time. 

If however the user decides to delete all contents of the ~/extensions/unziped directory, and wants to run the pipeline on a bigger dataset of extensions (i.e. a dataset containing extensions that are not inside the **regulrar_names.json** file  ), we specifically provide some helper scripts inside the python_code/helper_scripts directory to allow the user to do so. The user needs to call these scripts first before calling the pipeline in this case.





### 4. How to use:

To run the pipeline, the path to a valid JSON file must be provided, that contains the total set of IDs and their versions in a chronological order.

We provide two example datasets here, the **regular_names.json** set which contains 226.221 extension IDs, and the **sample_set.json** which contains 25 arbitrary IDs that contain at least one update (good for testing changes).

Assuming the user wants to run the pipeline on all extensions in the **regular_names.json** , he has to do the following 

- Change current directory to  ~/python_code/

- Execute the following commands in the given order: 

  - `$ python3 collect_permissions.py -parse_manifest ../regular_names.json` 
  - `$ python3 static_analysis.py -analyze ../regular_names.json`
  - `$ python3 collect_permissions.py -compare_changes ../regular_names.json`
  - `$ python3 static_analysis.py -compare_changes ../regular_names.json`
  - `$ python3 merge_tables.py -merge_overview ../regular_names.json`
  - `$ python3 merge_tables.py -merge_changes ../regular_names.json`

  (if another json file with IDs is used instead, just change the file part when executing the commands)





What each command does is explained below:

- `collect_permissions.py` is called to parse the manifest of each extension version, collect all relevant information from it and store it inside the `permissions_overview` table. This step takes at most 6 minutes when run on 30 processes
- `static_analysis.py` is called to statically analyse each extension versions for each ID. First all zip files content are extracted, then manifest data is collected that instructs the pipeline on where to look for script files (e.g. background scripts / background pages, WAR pages / scripts etc). The pipeline analyzes all files that could be found and collects all relevant API calls for each relevant script file. Finally, the results are stored in the `api_overview` table, while all data inside the ID_version directory is deleted, with the only exception being the manifest. This step takes at most 10 hours, when run on 30 processes 





The next four commands do not access any extension files / manifests anymore. Instead they just use the results inside the `api_overview` and `permissions_overview` tables to compute the final results. 

- `collect_permissions.py` is called to compare changes in requested permissions between versions for each ID. It does so by analysing the data inside the table `permissions_overview`. Results are stored inside the table `permission_changes`. Estimated time is 5 minutes when running on 30 processes.
- `static_analysis.py` is called to compare changes in API usage between versions for each ID. It does so by analysing the data inside the table `api_overview`. Results are stored inside the table `api_changes`. Estimated time is 5 minutes when running on 30 processes.



Finally, the last two commands simply merge all data computed so far to produce the final results, and store them in the `overview_complete` and `changes_complete` tables.

- `merge_tables` is first called to combine the data from both `api_overview` and `permissions_overview` tables and store the results inside the `overview_complete` table. Estimated time is 6 minutes running on 30 processes.
- `merge_tables` is then called to combine the data from the tables `api_changes` and `permission_changes` , and store the results inside the `changes_complete` table. Some data from `overview_complete` is also used to better understand the usage of permissions.



Note: while all individual commands produce results (namely the error_log and the resulting table content in JSON format, both store in the results directory), results of the intermediate commands do not yet contain complete information. e.g. `api_overview` and `api_changes` contain information about used APIs, but not yet about the complete list of permissions utilized (e.g. utilization of special permissions such as background, activeTab etc is not yet displayed on those tables). This is not an error, but the way the pipeline operates. This must be taken into account when inspecting intermediate results.