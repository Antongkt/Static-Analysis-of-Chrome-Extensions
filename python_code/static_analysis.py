import json
import os
import psycopg2
import zipfile
import re
import resource
from tqdm import tqdm
from bs4 import BeautifulSoup
from subprocess import check_output
import sys
import argparse
import shutil
import ast
from jsoncomment import JsonComment
from jsmin import jsmin
import jstyleson



import multiprocessing as mp


api_dictionary = {}
prefix = {}

# crawls scripts to find additional imported scripts
def crawlScripts(root_path, scripts):
    additional_scripts = set()
    already_checked = set()
    for script in scripts:
        already_checked.add(script)
        additional_scripts = additional_scripts.union(crawlScriptsIter(root_path, set([script]), already_checked))
        already_checked = already_checked.union(additional_scripts)
    return additional_scripts



# crawls a list of scripts for imported scripts,
# iteratively crawls every script found for more scripts
def crawlScriptsIter(root_path,scripts, already_checked):
    result = set()
    for script in scripts:
        prefix = extractPrefix(script)      #extract the prefix of the script, that is importing other scripts
        if (script.startswith('/')):
            script = '.' + script
        file_path = root_path + script
        if os.path.exists(file_path): #script found locally, we can try parsing the AST and look for additional import / require statements
            try:
                output = check_output(['node', '../js_code/collectNestedScripts.js', file_path, root_path + prefix])
                output = output.decode("utf-8")
                if (output != '\n'):
                    output = output.strip()
                    scripts_found = output.split(',')
                    scripts_found = list(scripts_found)
                    for i in scripts_found:
                        if i.startswith('/'):
                            i = '.' + i
                        else:
                            i = prefix + i
                        i = i.replace('/./', '/')       # clear out recursive ./
                        i = './' + os.path.relpath(i)   # clear out ../
                        if i not in already_checked:
                            result.add(i)
                            already_checked.add(i)
            except Exception as e:
                print("Script could not be parsed by AST: ")
                print(file_path)
    if not result:
        return result
    else:
        return result.union(crawlScriptsIter(root_path, result, already_checked))
        


        
# crawls a list of HTML pages, for imported script files as well as inline scripts
def crawlPages(root_path,pages):
    script_files = set()
    scripts = []
    for page in pages:
        prefix = extractPrefix(page)
        sources = []
        if (page.startswith('/')):
            page = '.' + page
        path = root_path + page
        if not (os.path.exists(path)):
            print('PAGE NOT EXISTING LOCALLY: ' + path)
            continue
        else:
            try:
                with open(path) as fp:
                    soup = BeautifulSoup(fp, 'html.parser')
                sources = soup.findAll('script',{"src":True})
                for i in sources:
                    script_name = i.get('src')
                    if (script_name.startswith('/')):       #absolute path to script is used in the script source, in this case extension root directory
                        script_files.add('.' + script_name)    
                    else:
                        script_files.add(prefix + script_name)   #relative path to script is used, if this html file has a path prefix we need to store it
                sources = soup.findAll('script',{"src":False})
                for i in sources:
                    scripts.append(i.text)
            except:
                print('COULD NOT PARSE HTML FILE WITH BEAUTIFULSOUP: ' + page)
                continue
                
    return (script_files, scripts)
                



    


#Collect all APIs used by:
# the list of background scripts found
# the list of content scripts found
# the inline scripts found
def collectAPIs(root_path, background_scripts, script_snipets, content_scripts):
    d = {}
    d['background_script_api_info'] = {}
    all_apis = set()
    #Crawl all script files for API usage first
    for script in background_scripts:
        path = '../js_code/collectAPIs.js'
        script = script.replace('/./', '/')
        if (script.startswith('/')):    #some trimming of the names, so that no scripts start with no / or ./ in their name (easier comparison for changes later)           
            script = '.' + script
        if (script.startswith('./')):
            script = script[2:]
        file_path =  root_path + script
        #Call our javascript static analysis file on each script, receive the output
        if os.path.exists(file_path): #script found locally, we can try parsing the AST and look for additional import / require statements
            try:
                output = check_output(['node', path, file_path])
                tmp = output.decode("utf-8")
                if (tmp == '\n'):
                    d['background_script_api_info'][script] = {}
                    continue
                else:
                    tmp = tmp.strip()
                    apis = tmp.split(',')
                    d['background_script_api_info'][script] = list(apis)
            except:
                print('COULD NOT ANALYZE API CALLS FOR FILE: ' + file_path)
                continue
        
        


    #Next, crawl all <script></script> code snipets inside html files for API usage
    tmp_dir = root_path + 'code_snipet_directory'
    if os.path.isdir(tmp_dir):
        print('Directory already exists')
    else:
        path = '../js_code/collectAPIs.js'
        try:
            os.mkdir(tmp_dir)
        except:
            print('cant create directory')
        snipet_apis = set()
        for s in script_snipets:
            try:
                file_path = tmp_dir + '/' + str(script_snipets.index(s)) + '.js'
                with open(file_path, 'w') as f:
                    f.write(s)
                output = check_output(['node', path, file_path])
                tmp = output.decode("utf-8")
                if (tmp == '\n'):
                    os.remove(file_path)
                    continue
                else:
                    tmp = tmp.strip()
                    apis = tmp.split(',')
                    snipet_apis = snipet_apis.union(set(apis))
                os.remove(file_path)
            except:
                print('CANNOT DELETTE FILE')
                print('\n' + file_path)
                continue
        #directory = Path(tmp_dir)
        #for item in directory.iterdir():    #there shouldnt be any items left inside the folder but just to be sure delette any items present
            #item.unlink
        try:
            os.rmdir(tmp_dir)
        except:
            print('cant delette dir')
        d['background_script_api_info']['script_snipet_apis'] = snipet_apis
        
    
    



    global api_dictionary
    result = {}
    result['background_script_api_info'] = {}
    for key in d['background_script_api_info'].keys():
        result['background_script_api_info'][key] = {}
        relevant, irrelevant = filterAPIs(d['background_script_api_info'][key])
        result['background_script_api_info'][key]['relevant'] = relevant
        result['background_script_api_info'][key]['irrelevant'] = irrelevant
        all_apis = all_apis.union(relevant)
        
    d['content_script_api_info'] = {}
    for script in content_scripts:
        path = '../js_code/collectAPIs.js'
        script = script.replace('/./', '/')
        if (script.startswith('/')):    #some trimming of the names, so that no scripts start with no / or ./ in their name (easier comparison for changes later)           
            script = '.' + script
        if (script.startswith('./')):
            script = script[2:]
        file_path =  root_path + script
        #Call our javascript static analysis file on each script, receive the output
        if os.path.exists(file_path): #script found locally, we can try parsing the AST and look for additional import / require statements
            try:
                output = check_output(['node', path, file_path])
                tmp = output.decode("utf-8")
                if (tmp == '\n'):
                    d['content_script_api_info'][script] = []
                    continue
                else:
                    tmp = tmp.strip()
                    apis = tmp.split(',')
                    relevant_apis = set()
                    for api in list(apis):
                        if api.startswith('storage.') or api.startswith('sendNativeMessage.') or api.startswith('connectNative.'):
                            relevant_apis.add(api)
                            all_apis.add(api)
                    d['content_script_api_info'][script] = list(relevant_apis)
            except Exception as e:
                print('COULD NOT ANALYZE API CALLS FOR CONTENT SCRIPT: ' + file_path)
                print(e)
                continue
    result['content_script_api_info'] = d['content_script_api_info']
    result['permissions_in_use'] = getPermissionsInUse(all_apis)
    return result

        
    
    
# given a list of detected API calls will find
# all permissions in use
def getPermissionsInUse(apis):
    global api_dictionary
    permissions = api_dictionary.keys()
    result = {}
    for api in apis:
        if api == 'document.execCommand(paste)' and 'clipboardRead' not in result:
            x = []
            x.append(api)
            result['clipboardRead'] = x
        elif api == 'document.execCommand(cut)' or api == 'document.execCommand(copy)':
            if 'clipboardWrite' in result:
                if api not in result['clipboardWrite']:
                    x = result['clipboardWrite']
                    x.append(api)
                    result.update({'clipboardWrite': x})
            else:
                x = []
                x.append(api)
                result['clipboardWrite'] = x
        elif 'runtime.connectNative' in api or 'runtime.sendNativeMessage' in api:
            if 'nativeMessaging' in result:
                if api not in result['nativeMessaging']:
                    x = result['nativeMessaging']
                    x.append(api)
                    result.update({'nativeMessaging': x})
            else:
                x = []
                x.append(api)
                result['nativeMessaging'] = x
        elif 'navigator.geolocation' in api:
            if 'geolocation' in result:
                if api not in result['geolocation']:
                    x = result['geolocation']
                    x.append(api)
                    result.update({'geolocation': x})
            else:
                x = []
                x.append(api)
                result['geolocation'] = x
        else:
            tmp = api.split('.', 1)[0]
            if tmp in permissions:
                if tmp in result:
                    if api not in result[tmp]:
                        x = result[tmp]
                        x.append(api)
                        result.update({tmp: x})
                else:
                    x = []
                    x.append(api)
                    result[tmp] = x
            
    return result


# splits a list of APIs into relevant and irrelevant ones
# relevant are the ones from developer google docs,
# irrelevant are the ones with no permissions needed etc
def filterAPIs(apis):
    relevant_apis = []
    irrelevant_apis = []
    for api in apis:
        #special APIs checked first
        if api == 'document.execCommand(paste)' or api == 'document.execCommand(cut)' or api == 'document.execCommand(copy)' or api.startswith('navigator.geolocation'):
            relevant_apis.append(api)
        elif 'runtime.connectNative' in api or 'runtime.sendNativeMessage' in api:
            relevant_apis.append(api)
        else:
            parts = api.split('.')
            relevant = checkAPI(parts)
            if (relevant):
                relevant_apis.append(api)
            else:
                irrelevant_apis.append(api)
    return (relevant_apis,irrelevant_apis)


# filters out irrelevant APIs from a list of APIs that were detected
# from crawling content scripts
def filter_cs_apis(apis):
    relevant_apis = []
    irrelevant_apis = []
    storage = set()
    for api in apis:
        if api.startswith('i18n') or api.startswith('storage') or api.startswith('runtime'):
            relevant_apis.append(api)
            if api.startswith('storage'):
                storage.add(api)
        else:
            irrelevant_apis.append(api)
    return (relevant_apis,irrelevant_apis, storage)

# checks if an the API is in relevant APIs
def checkAPI(parts):
    global api_dictionary
    return iterCheck(api_dictionary, parts)

# iteratively checks if the API parts point to some valid API from the list of known APIs
# e.g. chrome.storage.local will be split in three parts, chrome will be first matched,
# then storage, then local. chrome.runtime will not be matched etc
def iterCheck(dict, parts):
    #case1: all parts were matched in the dictionary, valid API
    #case2: more parts existing but we reached the end of the dictionary,
    # API is valid but we might have a wrong tail
    if (len(parts) == 0 or len(dict) == 0):
        return True
    next_level = parts[0]
    if (next_level in dict):
        del parts[0]
        if (isinstance(dict, list)):
            new_dict = {}
        else:
            new_dict = dict[next_level]
        return iterCheck(new_dict, parts)
    elif ('method' in dict) or ('type' in dict) or ('property' in dict) or ('event' in dict):
        b = False
        if ('method' in dict):
            b = b or iterCheck(dict['method'], parts)
        if ('type' in dict):
            b = b or iterCheck(dict['type'], parts)
        if ('property' in dict):
            b = b or iterCheck(dict['property'],parts)
        if ('event' in dict):
            b = b or iterCheck(dict['event'], parts)
        return b
    else:
        return False


# extracts the prefix from a given file path
# in case / is used, the prefix is ./ (symbolizes the extension root directory)
def extractPrefix(x):
    pos = x.rfind("/")
    if pos == -1:
        prefix = "./"        #file path from root directory is ./
    elif pos ==0:
        prefix = "./"
    else:
        prefix = x[0 : pos + 1]  #file path from root directory is everything until the last occurence of / (meaning, everything before file name)
    return prefix


# analyzes statically all versions of the given extension ID
def analyze_process(stringified_dict):
    f = json.loads(stringified_dict)
    id, versions = f.popitem()
    errors = ''
    d = {}
    d['versions'] = {}
    con = psycopg2.connect(
    host = 'localhost',
    database = 'extension_updates',
    user = 'anton',
    password = 'vgJttLSune5ijQfg3ch6ujh4AgLw{nLs7lfJ')
    try:
        with con:
            cur = con.cursor()
            query = "SELECT info AS x FROM permissions_overview WHERE id='" + id + "';"
            cur.execute(query)
            result = cur.fetchall()[0][0]   #list of tuples is returned
    except:
        return 'COULD NOT GET INFO FROM DATABASE'
    if id == 'cgjdoogakiemolfnpmmggijdnpghklab' or id == 'mdccoejpogkcfnkddfdhgkmlbhhphmoo' or id == 'mbblfalbndfkpfnlimjnaooandenimpj':
        #Don't analyze these IDs or our pipeline will be stuck for a long time on them
        for version in versions:
            d['versions'][version] = {}
            d['versions'][version]['valid'] = 0
        return errors  
    for version in versions:
        root_path = ''
        d['versions'][version] = {}
        if result['versions'][version]['valid'] == 0:
            d['versions'][version]['valid'] = 0
            continue
        else:
            root_path = '../extensions/unziped/' + id + '_' + version + '/'
            zip_file_path = '../extensions/' + id + '_' + version + '.zip'
            manifest_path = root_path + 'manifest.json'
            manifest_data = {}
            #first unzip
            try:
                with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                    print('extracting into: ' + root_path)
                    zip_ref.extractall(root_path)
            except:
                errors += 'COULD NOT UNZIP ID: '
                errors += zip_file_path
                cleanup(root_path)
                d['versions'][version]['valid'] = 0
                continue
        valid = True
        if not os.path.exists(manifest_path):
            valid = False
            errors += 'Manifest does not exist, likely bad zip file: '
            errors += manifest_path
            d['versions'][version]['valid'] = 0
            cleanup(root_path)
            continue
        else:
            try:
                manifest = open(manifest_path, 'r', encoding='utf-8-sig')
            except:
                manifest = open(manifest_path, "rb").read()
            if manifest is not None and manifest != "":
                try:
                    manifest_data = json.loads(manifest)
                except:
                    try:
                        manifest_data = ast.literal_eval(manifest)
                    except:
                        try:
                            json_comment = JsonComment()
                            manifest_data = json_comment.loads(manifest)
                        except:
                            try:
                                manifest_data = jstyleson.loads(manifest)
                            except:
                                try:
                                    minified = jsmin(manifest)
                                    manifest_data = json.loads(minified)
                                except:
                                    try:
                                        manifest = open(manifest_path, 'r', encoding='utf-8-sig', errors='ignore').read()
                                        manifest_data = json.loads(manifest)
                                    except:
                                        errors += "\n Trouble parsing manifest: "
                                        errors += manifest_path
                                        valid = False
            else:
                errors += "\n Trouble parsing manifest: "
                errors += manifest_path
                valid = False
            if valid == False:
                d['versions'][version]['valid'] = 0
                cleanup(root_path)
                continue
                
            
            content_scripts = set()
            background_scripts = set()
            background_pages = set()
            war_pages = set()
            war_scripts = set()
            popup_page = ''



            # 1. FIND ALL CONTENT SCRIPTS
            
            if ('content_scripts' in manifest_data):
                try:
                    tmp = manifest_data['content_scripts']
                    for i in tmp:
                        content_scripts = content_scripts.union(set(i['js']))
                except:
                    errors += 'invalid content script key in manifest: '
                    errors += str(tmp)



            # 2. FIND ALL BACKGROUND SCRIPTS / PAGE
             
            if ('background' in manifest_data): #TODO: ensure to check if list or single script / page. If single append, if list iterate
                mv = 2
                tmp = manifest_data['background']
                try:
                    if ('manifest_version' in manifest_data):
                        mv = manifest_data['manifest_version']
                    if (mv == 2):
                        if 'scripts' in tmp:
                            for i in tmp['scripts']:
                                try:
                                    background_scripts.add(i)
                                except:
                                    continue
                        elif 'page' in tmp:
                            page = tmp['page']
                            background_pages.add(page)
                        elif 'service_worker' in tmp:
                            background_scripts.add(tmp['service_worker'])
                    elif (mv == 3):
                        if 'service_worker' in tmp:
                            background_scripts.add(tmp['service_worker'])
                except Exception as e:
                    errors += 'Background script / page / worker invalid format: '
                    errors += str(e)
                    errors += '\nProblematic id: '
                    errors += root_path


            # 3. FIND ALL WAR PAGES + SCRIPTS
            wars = []
            if ('web_accessible_resources') in manifest_data:
                wars += manifest_data['web_accessible_resources']
                mv = 2
                try:
                    if ('manifest_version' in manifest_data):
                        mv = manifest_data['manifest_version']
                except:
                    mv = 2
                for i in wars:
                    if mv == 2:
                        try:    #We use a try - except block because some war entries are a dictionary (?)
                            if i.endswith('.js'):
                                war_scripts.add(i)
                            elif i.endswith('.html'):
                                war_pages.add(i)
                        except:
                            errors += 'WAR Entry invalid format: '
                            errors += str(i)
                            errors += '\nProblematic id: ' + root_path
                            continue
                    elif mv == 3:
                        try:
                            if isinstance(i, dict):
                                if 'resources' in i:
                                    tmp = i['resources']
                                    for g in tmp:
                                        if g.endswith('.html'):
                                            war_pages.add(g)
                                        elif g.endswith('.js'):
                                            war_scripts.add(g)
                                    if 'js' in i:
                                        tmp = i['js']
                                        for g in tmp:
                                            if g.endswith('.html'):
                                                war_pages.add(g)
                                            elif g.endswith('.js'):
                                                war_scripts.add(g)
                        except:
                            errors += 'WAR Entry invalid format: '
                            errors += str(i)
                            errors += '\nProblematic id: ' + root_path
                            continue


            # 4. FIND THE POPUP PAGE IF THERE IS ONE
            if ('browser_action' in manifest_data):
                if 'default_popup' in manifest_data['browser_action']:
                    try:
                        popup_page = manifest_data['browser_action']['default_popup']
                    except:
                        errors += 'WAR Entry invalid format: '
                        errors += str(manifest_data['browser_action']['default_popup'])
                        errors += '\nProblematic id: ' + root_path
            elif ('action' in manifest_data):
                if 'default_popup' in manifest_data['action']:
                    try:
                        popup_page = manifest_data['action']['default_popup']
                    except:
                        errors += 'WAR Entry invalid format: '
                        errors += str(manifest_data['action']['default_popup'])
                        errors += '\nProblematic id: ' + root_path


            # MERGE ALL PAGES FOUND IN ONE LIST, AND ALL SCRIPTS FOUND IN ANOTHER LIST
            #TODO: use set operation instead of list?
            pages = background_pages.union(war_pages)
            if (popup_page != '') and isinstance(popup_page, str):
                pages.add(popup_page)
            total_scripts = war_scripts.union(background_scripts)


            # 5. CRAWL ALL PAGES FOUND SO FAR FOR IMPORTED / LOCAL SCRIPTS
            # ADD ALL NEWLY FOUND SCRIPTS FILES TO THE LIST OF TOTAL SCRIPT FILES
            tmp = crawlPages(root_path, pages)
            total_scripts = total_scripts.union(tmp[0])         #add all script files found to the list of script files so far
            script_snipets = tmp[1]         #add all <script></script> code snippets into a list, we later write them into js files and analyze them
              #remove duplicates by making a set
            #total_scripts = total_scripts.difference(set(content_scripts)) #remove files that we know are contect scripts, no need to look for APIs in them
            total_background_scripts = set()
            for i in total_scripts:
                if i.startswith('/'):
                    i = '.' + i
                i = './' + i
                i = i.replace('/./', '/')
                i = './' + os.path.relpath(i)
                total_background_scripts.add(i)

            total_content_scripts = set()
            for i in content_scripts:
                if i.startswith('/'):
                    i = '.' + i
                i = './' + i
                i = i.replace('/./', '/')
                i = './' + os.path.relpath(i)
                total_content_scripts.add(i)
            
            # 6. FINALLY, CRAWL ALL SCRIPT FILES FOUND, TO FIND ADDITIONAL IMPORTED SCRIPTS (either via "import" or "require" statements) RECURSIVELY
            additional_scripts = crawlScripts(root_path, total_background_scripts)
            additional_content_scripts = crawlScripts(root_path, total_content_scripts)
            total_background_scripts = total_background_scripts.union(additional_scripts)
            total_content_scripts = total_content_scripts.union(additional_content_scripts)
            total_content_scripts = total_content_scripts.difference(total_background_scripts) #filter out background scripts
            #total_background_scripts = total_background_scripts.difference(set(content_scripts))    #TODO: NORMALLY THERE SHOULD BE NO CONTENT SCRIPTS IN THIS LIST, BUT FOR NOW FILTER OUT CS ANYWAY TO BE SAFE


           
            # 7. Statically analyze all scripts found, to find API calls
            resultt = collectAPIs(root_path, total_background_scripts, script_snipets, total_content_scripts)
            d['versions'][version]['valid'] = 1
            d['versions'][version]['background_script_api_info'] = resultt['background_script_api_info']
            d['versions'][version]['content_script_api_info'] = resultt['content_script_api_info']
            d['versions'][version]['permissions_in_use'] = resultt['permissions_in_use']
            
            cleanup(root_path)

    #ALL VERSIONS OF THIS ID WERE ANALYZED
    #STORE RESULT IN DATABASE
    
    with con:
        cur = con.cursor()
        json_data = json.dumps(d)
        query = """INSERT INTO api_overview (id, info) VALUES (%s, %s::json)""" 
        try:
            cur.execute(query, (id, json_data))
        except Exception as e:
            errors += '\n COULD NOT WRITE INTO TABLE overview FOR ID: ' 
            errors += str(id)
            errors += '\n QUERY: '
            errors += str(query)
            errors += '\n exception: '
            errors += str(e)
            con.rollback()
        else:
            con.commit()
    #cleanup the folder inside unziped, delette all files except for manifest
    return errors



# statically analyzes a dictionary of (extension_id : versions) pairs by using 30 processess
def analyze(d):
    error_file = ''
    dataset = []
    for item in d.items():
        dataset.append(stringify(item))
        
    with mp.Pool(30) as pool:
         for x in tqdm(pool.imap_unordered(analyze_process, dataset), total=len(dataset)):
                error_file += x
    with open('../results/error_api_overview.txt', 'w') as f:
        f.write(error_file)

# used to stringify dictionary entries before passing them to each process, by using imap_unordered
def stringify(x):
    id = x[0]
    versions = x[1]
    d = {}
    d[id] = versions
    return json.dumps(d)

# For a given extension ID and all it's versions, will detect changes
def compare_changes_process(stringified_dict):
    f = json.loads(stringified_dict)
    id, versions = f.popitem()
    errors = ''
    result = {}
    api_data = {}
    con = psycopg2.connect(
    host = 'localhost',
    database = 'extension_updates',
    user = 'anton',
    password = 'vgJttLSune5ijQfg3ch6ujh4AgLw{nLs7lfJ')
    with con:
        cur = con.cursor()
        query = "SELECT info AS x FROM api_overview WHERE id='" + id + "';"
        try:
            cur.execute(query)
        except Exception as e:
            errors += 'Could not read form database for id: '
            errors += id
            errors += '\n Exception:'
            errors += str(e)
            con.rollback()
            return errors
        api_data = cur.fetchall()[0][0]   #list of tuples is returned
    
    result['update_info'] = {}
    validUpdates = []
    for i in range(len(versions)):
        if api_data['versions'][versions[i]]['valid'] == 1:
            validUpdates.append(versions[i])
    updates_with_change = 0
    
    if (len(validUpdates) >= 2):        #need at least 2 valid entries to check changes
        indexA = 0
        indexB = 1
        result['start_version'] = validUpdates[indexA]
        if 'tabs' in api_data['versions'][validUpdates[indexA]]['permissions_in_use']:
            value = api_data['versions'][validUpdates[indexA]]['permissions_in_use'].pop('tabs')
            tabs_apis = check_tabs_in_use(value)
            if len(tabs_apis) > 0:
                api_data['versions'][validUpdates[indexA]]['permissions_in_use']['tabs'] = tabs_apis
        result['start_utilized_permissions'] = api_data['versions'][validUpdates[indexA]]['permissions_in_use']
        result['update_info'] = {}
        #for each update, note down previous update, changes etc
        while (indexB < len(validUpdates)):
            current_version = validUpdates[indexB]
            previous_version = validUpdates[indexA]


            if 'tabs' in api_data['versions'][current_version]['permissions_in_use']:
                value = api_data['versions'][current_version]['permissions_in_use'].pop('tabs')
                tabs_apis = check_tabs_in_use(value)
                if len(tabs_apis) > 0:
                    api_data['versions'][current_version]['permissions_in_use']['tabs'] = tabs_apis

            print('COMPARING VERSIONS: ' + current_version + ' AND ' + previous_version)
            tmp, major_changes = compare_versions(api_data['versions'][current_version]['permissions_in_use'], api_data['versions'][previous_version]['permissions_in_use'])
            if (major_changes):
                result['update_info'][current_version] = {}
                result['update_info'][current_version]['utilized_permissions'] = api_data['versions'][current_version]['permissions_in_use']
                result['update_info'][current_version]['previous_version'] = previous_version
                result['update_info'][current_version]['new_utilized_permissions'] = list(tmp['new_utilized_permissions'])
                result['update_info'][current_version]['no_longer_utilized_permissions'] = list(tmp['no_longer_utilized_permissions'])
                updates_with_change += 1
            indexB += 1
            indexA += 1
    

        total_versions = len(versions)
        valid_versions = len(validUpdates)
        jsondata = json.dumps(result)
        with con:
            cur = con.cursor()
            query = "INSERT INTO api_changes (id, api_info, total_versions, valid_versions, api_change_updates) VALUES (%s, %s::json, %s, %s, %s)"
            try:
                cur.execute(query, [id, jsondata, total_versions, valid_versions, updates_with_change])
            except Exception as e:
                errors += 'Exteption trying to write into database for id : '
                errors += id
                errors += '\n Exception: '
                errors += str(e)
                con.rollback()
            else:
                con.commit()
        return errors






# compares two extensions versions to find changes in utilized permissions
def compare_versions(current_version, previous_version):
    major_changes = False
    d = {}
    permissions_in_use_before = set(previous_version.keys())
    permissions_in_use_after = set(current_version.keys())
    if permissions_in_use_after == permissions_in_use_before:
       major_changes = False
    else:
        major_changes = True
        d['new_utilized_permissions'] = permissions_in_use_after.difference(permissions_in_use_before)
        d['no_longer_utilized_permissions'] = permissions_in_use_before.difference(permissions_in_use_after)
    return d, major_changes

# limits the memory used
def limit_memory(maxsize):
    """ Limiting the memory usage to maxsize (in bytes), soft limit. """
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (maxsize, hard))




# compares changes 
def compare_changes_multiprocess(d):
    dataset = []
    for item in d.items():
        dataset.append(stringify(item))
    error_log = ''
    with mp.Pool(30) as pool:
         for x in tqdm(pool.imap_unordered(compare_changes_process, dataset), total=len(dataset)):
                error_log += str(x)
    
    with open('../results/error_log_api_changes.txt', 'w') as f:
        f.write(error_log)


#empties the database tables
def empty_table(table):
    con = psycopg2.connect(
    host = 'localhost',
    database = 'extension_updates',
    user = 'anton',
    password = 'vgJttLSune5ijQfg3ch6ujh4AgLw{nLs7lfJ')
    with con:
        cur = con.cursor()
        cur.execute('TRUNCATE TABLE ' + table)
        try:
            con.commit()
        except:
            print('COULD NOT TRUNCATE TABLE BEFORE STARTING PROCESS, ABORTING')
            con.rollback()
            exit()
        else:
            exit
# retrieves the results from the database
# and dumps them in a JSON file
def collect_results(table):
    d = {}
    con = psycopg2.connect(
    host = 'localhost',
    database = 'extension_updates',
    user = 'anton',
    password = 'vgJttLSune5ijQfg3ch6ujh4AgLw{nLs7lfJ')
    with con:
        cur = con.cursor()
        cur.execute('SELECT * FROM ' + table)
        rows = cur.fetchall()
        for row in rows:
            d[row[0]] = row[1]
            if (table == 'permission_changes'):
                d[row[0]]['total_versions'] = row[2]
                d[row[0]]['valid_versions'] = row[3]
                d[row[0]]['permission_change_updates'] = row[4]
            elif (table == 'api_changes'):
                d[row[0]]['total_versions'] = row[2]
                d[row[0]]['valid_versions'] = row[3]
                d[row[0]]['api_change_updates'] = row[4]
    
    with open('../results/results_' + table + '.json', 'w') as f:
        json.dump(d, f, indent=4)

# delettes all files in the directory except for the manifest
def cleanup(root_path):
    all = os.listdir(root_path)
    for i in all:
        path = root_path + i
        try:
            if os.path.isfile(path):
                if i != 'manifest.json':
                    os.unlink(path)
            else:
                shutil.rmtree(path)
        except:
            continue



#checks if tabs is utilized according to our definition, based on the chrome developer page
#to see whether active tab is utilized instead or at the same time as tabs, we have to check requested permissions and whether webRequest is used
#that is performed by the merging script
def check_tabs_in_use(tmp):
    tabs_apis = []
    for i in tmp:
        if i == 'tabs.Tab.url' or i == 'tabs.Tab.pendingUrl' or i == 'tabs.Tab.title' or i == 'tabs.Tab.favIconUrl':
            tabs_apis.append(i)
        if i == 'tabs.captureVisibleTab' or i == 'tabs.executeScript' or i == 'tabs.insertCSS' or i == 'tabs.removeCSS':
            tabs_apis.append(i)

    return tabs_apis



limit_memory(20*10**9)  # Limiting the memory usage to 20GB
parser = argparse.ArgumentParser(description="This script is used to statically analyze extension files and collect data about API usage (and changes thereof) between versions.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("-analyze", type=str, help='statically analyze and put collected data in the database. NOTE: folders for data to be unziped must exist already!')
parser.add_argument("-compare_changes", type=str, help='analyze data from parse_manifest to detect changes in permissions between versions. NOTE: -analyze must be used first!')

with open('chrome_api_info3.json', 'r') as f:
    api_dictionary = json.load(f)


args = parser.parse_args()
config = vars(args)
d = {}
dd = {}
api_dictionary = {}
result = {}
with open('chrome_api_info3.json', 'r') as f:
    api_dictionary = json.load(f)


if config['analyze']:
    with open(config['analyze'], 'r') as f:
        d = json.load(f)
    empty_table('api_overview')
    analyze(d)
    collect_results('api_overview')
elif config['compare_changes']:
    with open(config['compare_changes'], 'r') as f:
        d = json.load(f)
    empty_table('api_changes')
    compare_changes_multiprocess(d)
    collect_results('api_changes')




