import json
import os
import psycopg2
import resource
from tqdm import tqdm
import multiprocessing as mp
from psycopg2 import sql
import argparse






# for a given ID and all versions, merges the respective entries for this ID
# from the tables api_changes and permission_changes
# resulting merged entry is put into changes_complete
def merge_changes_process(stringified_dict):
    f = json.loads(stringified_dict)
    id, versions = f.popitem()
    api_changes = {}
    permission_changes = {}
    overview = {}
    total_versions = 0
    total_valid_versions = 0
    permission_change_versions = 0
    api_change_versions = 0
    permission_and_api_change_versions = 0
    errors = ''
    con = psycopg2.connect(
    host = 'localhost',
    database = 'extension_updates',
    user = 'anton',
    password = 'vgJttLSune5ijQfg3ch6ujh4AgLw{nLs7lfJ')
    
    with con:
        cur = con.cursor()

        query = "SELECT info FROM overview_complete WHERE id='" + id + "';"
        try:
            cur.execute(query)
        except Exception as e:
            errors += 'Could not read form database for id: '
            errors += id
            errors += '\n Exception:'
            errors += str(e)
            con.rollback()
            return errors
        try:
            overview = cur.fetchall()[0][0]
        except:
            return 'ID no in table ' + str(id)

        query = "SELECT * FROM permission_changes WHERE id='" + id + "';"
        try:
            cur.execute(query)
        except Exception as e:
            errors += 'Could not read form database for id: '
            errors += id
            errors += '\n Exception:'
            errors += str(e)
            con.rollback()
            return errors
        try:
            permission_data = cur.fetchall()[0]   #list of tuples is returned
        except:
            return 'ID no in table ' + str(id)
        permission_changes = permission_data[1]
        total_versions = permission_data[2]
        total_valid_versions = permission_data[3]
        permission_change_versions = permission_data[4]


        query = "SELECT * FROM api_changes WHERE id='" + id + "';"
        try:
            cur.execute(query)
        except Exception as e:
            errors += 'Could not read form database for id: '
            errors += id
            errors += '\n Exception:'
            errors += str(e)
            con.rollback()
            return errors
        try:
            api_data = cur.fetchall()[0]   #list of tuples is returned
        except:
            return 'ID no in table ' + str(id)
        api_changes = api_data[1]
        api_change_versions = api_data[4]
    
    result = {}
    start_version = permission_changes['start_version']     #first valid version
    result['start_version'] = start_version
    result['start_r_permissions'] = overview['versions'][start_version]['r_permissions']
    result['start_u_permissions'] = overview['versions'][start_version]['u_permissions']
    result['start_all_urls_flag'] = overview['versions'][start_version]['all_urls_flag']
    result['update_info'] = {}
    index = versions.index(start_version) + 1
    start_index = versions.index(start_version)
    last_version = start_version
    update_count = 0
    while index < len(versions):
        version = versions[index]
        
        if overview['versions'][version]['valid'] == 0:
            index += 1
            continue
        else:
            last_version_u = set(overview['versions'][last_version]['u_permissions'])
            current_version_u = set(overview['versions'][version]['u_permissions'])
            if not (version in api_changes['update_info'] or (last_version_u != current_version_u)):
                #no change here
                index +=1 
                continue
            result['update_info'][version] = {}
            update_count = index - start_index  #count how many updates have there been so far, from the first valid version
            result['update_info'][version]['previous_version'] = last_version
            result['update_info'][version]['update_count'] = update_count
            result['update_info'][version]['all_urls_flag'] = overview['versions'][version]['all_urls_flag']
            result['update_info'][version]['r_permissions'] = overview['versions'][version]['r_permissions']
            result['update_info'][version]['u_permissions'] = overview['versions'][version]['u_permissions']
            result['update_info'][version]['changes'] = {}
            tags = set()
            r_change = False
            u_change = False
            if version in permission_changes['updates']:
                r_change = True
                if permission_changes['updates'][version]['api_permissions_change'] == 1:
                    change_details = permission_changes['updates'][version]['api_permission_change_details']
                    # Here only note down mandatory permissions getting bigger or smaller in count.
                    # assign the respective tags
                    new_r_mandatory = set()
                    removed_r_mandatory = set()
                    if len(change_details['new_api_permissions']) > 0 or len(change_details['moved_to_mandatory']) > 0:
                        tags.add('r+')
                        new_r_mandatory = set(change_details['new_api_permissions']).union(set(change_details['moved_to_mandatory']))
                        if ('webRequest' in new_r_mandatory) or ('webRequestBlocking' in new_r_mandatory) or ('declarativeWebRequest' in new_r_mandatory) or ('declarativeNetRequest' in new_r_mandatory):
                            tags.add('c_r+')
                        result['update_info'][version]['changes']['new_r_mandatory'] = list(new_r_mandatory)
                    if len(change_details['deleted_api_permissions']) > 0 or len(change_details['moved_to_optional']) > 0:
                        tags.add('r-')
                        removed_r_mandatory = set(change_details['deleted_api_permissions']).union(set(change_details['moved_to_optional']))
                        result['update_info'][version]['changes']['removed_r_mandatory'] = list(removed_r_mandatory)
                host_permission_change = permission_changes['updates'][version]['host_permission_change']
                #mandatory host permission change is also a relevant tag
                if host_permission_change not in ['irrelevant', 'uncertain']:
                    tags.add(host_permission_change)
            if last_version_u != current_version_u:
                u_change = True
                added = current_version_u.difference(last_version_u)
                removed = last_version_u.difference(current_version_u)
                if len(added) > 0:
                    tags.add('u+')
                    result['update_info'][version]['changes']['new_u'] = list(added)
                if len(removed) > 0:
                    tags.add('u-')
                    result['update_info'][version]['changes']['removed_u'] = list(removed)
            
            
            if u_change and r_change:
                permission_and_api_change_versions += 1

            current_category = overview['versions'][version]['category']
            previous_category = overview['versions'][last_version]['category']
            result['update_info'][version]['transition_grade'] = get_grade(current_category, previous_category)
            result['update_info'][version]['tags'] = list(tags)
            last_version = version
        index += 1


            
    con = psycopg2.connect(
	host = 'localhost',
	database = 'extension_updates',
	user = 'anton',
	password = 'vgJttLSune5ijQfg3ch6ujh4AgLw{nLs7lfJ')
    with con:
        cur = con.cursor()
        json_data = json.dumps(result)
        query = """INSERT INTO changes_complete (id, info, total_versions, valid_versions, r_change_updates, u_change_updates, r_and_u_change_updates ) VALUES (%s, %s::json, %s, %s, %s, %s, %s)"""
        try:
            cur.execute(query, (id, json_data, total_versions, total_valid_versions, permission_change_versions, api_change_versions, permission_and_api_change_versions))
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
    return errors

                


# returns the difference in grade after an update
def get_grade(current, previous):
    previous_value = int(previous[1]) + previous.count('+')
    current_value = int(current[1]) + current.count('+')
    return current_value - previous_value
# uses 30 processess to merge the tables api_changes and permission_changes
# into one table called changes_complete
def merge_changes_multiprocess(d):
    dataset = []
    for item in d.items():
        dataset.append(stringify(item))
    errors = ''
    with mp.Pool(30) as pool:
         for x in tqdm(pool.imap_unordered(merge_changes_process, dataset), total=len(dataset)):
                errors += str(x)
    with open('../results/error_log_merge_changes.txt', 'w') as f:
        f.write(errors)


# uses 30 processess to merge the tables api_overview and permissions_overview
def merge_overview_multiprocess(d):
    dataset = []
    for item in d.items():
        dataset.append(stringify(item))
    errors = ''
    with mp.Pool(30) as pool:
         for x in tqdm(pool.imap_unordered(merge_overview_process, dataset), total=len(dataset)):
                errors += str(x)
    with open('../results/error_log_merge_overview.txt', 'w') as f:
        f.write(errors)


# for a given ID and all versions, merges the respective overview table entries
# the resulting merged entry is stored in the table overview_complete
def merge_overview_process(stringified_dict):
    f = json.loads(stringified_dict)
    id, versions = f.popitem()
    api_data = {}
    permission_data = {}
    errors = ''
    con = psycopg2.connect(
    host = 'localhost',
    database = 'extension_updates',
    user = 'anton',
    password = 'vgJttLSune5ijQfg3ch6ujh4AgLw{nLs7lfJ')
    with con:
        cur = con.cursor()
        query = "SELECT info AS x FROM permissions_overview WHERE id='" + id + "';"
        try:
            cur.execute(query)
        except Exception as e:
            errors += 'Could not read form database for id: '
            errors += id
            errors += '\n Exception:'
            errors += str(e)
            con.rollback()
            return errors
        permission_data = cur.fetchall()[0][0]   #list of tuples is returned
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
    
    result = {}
    result['versions'] = {}
    for version in versions:
        result['versions'][version] = {}
        if permission_data['versions'][version]['valid'] == 0 or api_data['versions'][version]['valid'] == 0:
            result['versions'][version]['valid'] = 0
        else:
            result['versions'][version]['valid'] = 1
            mv = permission_data['versions'][version]['manifest_version']
            result['versions'][version]['manifest_version'] = mv
            result['versions'][version]['split_permissions'] = permission_data['versions'][version]['split_permissions']
            result['versions'][version]['split_host_permissions'] = permission_data['versions'][version]['split_host_permissions']
            result['versions'][version]['all_urls_flag'] = permission_data['versions'][version]['all_urls_flag']
            result['versions'][version]['r_permissions'] = {}
            result['versions'][version]['r_permissions']['mandatory'] = permission_data['versions'][version]['permissions']['api_permissions']
            result['versions'][version]['r_permissions']['optional'] = permission_data['versions'][version]['permissions']['optional_api_permissions']

            if 'tabs' in api_data['versions'][version]['permissions_in_use']:
                value = api_data['versions'][version]['permissions_in_use'].pop('tabs')
                tabs_apis = check_tabs_in_use(value)
                if len(tabs_apis) > 0:
                    api_data['versions'][version]['permissions_in_use']['tabs'] = tabs_apis
            u_permissions = set(api_data['versions'][version]['permissions_in_use'].keys())
            all_r_permissions = set(permission_data['versions'][version]['permissions']['api_permissions']).union(set(permission_data['versions'][version]['permissions']['optional_api_permissions']))
            #check if special permissions are utilized
            if 'background' in all_r_permissions:
                #assume on use by default, since we cannot really trace it's utilization
                u_permissions.add('background')
            if 'unlimitedStorage' in all_r_permissions:
                #assume on use by default, since we cannot really trace it's utilization
                u_permissions.add('unlimitedStorage')
            if 'signedInDevices' in all_r_permissions:
                #assume on use by default since there is no chrome documentation available
                u_permissions.add('signedInDevices')
            if 'experimental' in all_r_permissions:
                #assume on use by default since there is no chrome documentation available
                u_permissions.add('experimental')
                #if webRequest and webRequestBlocking are both required, and webRequest APIs are used, webRequestBlocking is assumed to be on use too
                #because our approach of detecting utilization is based on API usage, and these two API permissions share APIs with each other
            if 'webRequest' in all_r_permissions and 'webRequestBlocking' in all_r_permissions and 'webRequest' in u_permissions:
                u_permissions.add('webRequestBlocking')
            if 'declarativeNetRequest' in u_permissions:
                #same approach as for webRequest and webRequestBlocking, declarativeNetRequest family of permissions all share APIs
                if 'declarativeNetRequestWithHostAccess' in all_r_permissions:
                    u_permissions.add('declarativeNetRequestWithHostAccess')
                if 'declarativeNetRequestFeedback' in all_r_permissions:
                    u_permissions.add('declarativeNetRequestFeedback')

            #If activeTab is requested, there are 4 cases that verify whether is in use according to our apporach
            if 'activeTab' in all_r_permissions:    #activeTab is requested, check cases
                if 'tabs' in u_permissions:     #case 1: sensitive tabs methods are utizilied
                    u_permissions.add('activeTab')
                elif 'webRequest' in u_permissions or 'webRequestBlocking' in u_permissions:  #case 2: webRequest or webRequestBlocking is utilized
                    u_permissions.add('activeTab')
                elif 'declarativeNetRequest' in u_permissions or 'declarativeNetRequestFeedback' in u_permissions or 'declarativeNetRequestWithHostAccess' in u_permissions:    #case 3: declarativeNetRequest API family is utizilied
                    u_permissions.add('activeTab')
                elif 'scripting' in u_permissions:  #case 4: scripting APIs are utilized
                    u_permissions.add('activeTab')
            result['versions'][version]['u_permissions'] = list(u_permissions)
            overprivileged = 0
            for p in all_r_permissions:
                if p not in u_permissions:
                    overprivileged = 1
            c_count = 0
            plus_count = 0
            if result['versions'][version]['all_urls_flag'] in ['both', 'mandatory', 'optional']:
                c_count = 0
                plus_count = 0
                if 'cookies' in all_r_permissions:
                    c_count += 1
                    if 'cookies' in u_permissions:
                        plus_count +=1
                if 'webRequest' in all_r_permissions and 'webRequest' in u_permissions: #webRequestblocking can only be requested additionally with webRequest, and is by default utilized if webRequest is utilized
                    plus_count += 1
                    c_count += 1
                elif ('declarativeNetRequest' in all_r_permissions or 'declarativeNetRequestWithHostAccess' in all_r_permissions or 'declarativeNetRequestFeedback' in all_r_permissions) and 'declarativeNetRequest' in u_permissions:
                    plus_count += 1
                    c_count += 1
                else:
                    if 'webRequest' in all_r_permissions or 'declarativeNetRequest' in all_r_permissions or 'declarativeNetRequestWithHostAccess' in all_r_permissions or 'declarativeNetRequestFeedback' in all_r_permissions:
                        c_count +=1
                if 'tabs' in all_r_permissions and 'tabs' in u_permissions:
                    c_count +=1
                    plus_count +=1
                elif 'scripting' in all_r_permissions and 'scripting' in u_permissions:
                    c_count +=1
                    plus_count +=1
                else:
                    if 'tabs' in all_r_permissions or 'scripting' in all_r_permissions:
                        c_count +=1
            category = 'c' + str(c_count)
            while plus_count > 0:
                category += '+'
                plus_count -= 1
            result['versions'][version]['category'] = category

                    
            result['versions'][version]['over_privileged'] = overprivileged
            
    con = psycopg2.connect(
	host = 'localhost',
	database = 'extension_updates',
	user = 'anton',
	password = 'vgJttLSune5ijQfg3ch6ujh4AgLw{nLs7lfJ')
    with con:
        cur = con.cursor()
        json_data = json.dumps(result)
        query = """INSERT INTO overview_complete (id, info) VALUES (%s, %s::json)"""
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
    return errors
            

            

#limits the memory usage           
def limit_memory(maxsize):
    """ Limiting the memory usage to maxsize (in bytes), soft limit. """
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (maxsize, hard))           


# used to created strings out of dictionary entries, to pass them to the processess
# with imap.unordered
def stringify(x):
    id = x[0]
    versions = x[1]
    d = {}
    d[id] = versions
    return json.dumps(d)




# special checks to detect whether the tabs permission is utilized
def check_tabs_in_use(tmp):
    tabs_apis = []
    for i in tmp:
        if i == 'tabs.Tab.url' or i == 'tabs.Tab.pendingUrl' or i == 'tabs.Tab.title' or i == 'tabs.Tab.favIconUrl':
            tabs_apis.append(i)
        if i == 'tabs.captureVisibleTab' or i == 'tabs.executeScript' or i == 'tabs.insertCSS' or i == 'tabs.removeCSS':
            tabs_apis.append(i)

    return tabs_apis


# empties a table in the database
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
# collects results from a table in the database
# and dumps them into a json file
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
            if (table == 'changes_complete'):
                d[row[0]]['total_versions'] = row[2]
                d[row[0]]['valid_versions'] = row[3]
                d[row[0]]['r_change_updates'] = row[4]
                d[row[0]]['u_change_updates'] = row[5]
                d[row[0]]['r_and_u_change_updates'] = row[6]
    
    with open('../results/results_' + table + '.json', 'w') as f:
        json.dump(d, f, indent=4)


limit_memory(20*10**9)  # Limiting the memory usage to 20GB
parser = argparse.ArgumentParser(description="This script is used to merge tables in the database, once they are filled up with data from the other two scripts", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("-merge_overview", type=str, help='merge the data from teh tables api_overview and permissions_overview, in a meaningful way')
parser.add_argument("-merge_changes", type=str, help='merge the data from the tables api_changes and permission_changes, in a meaningful way')





args = parser.parse_args()
config = vars(args)
d = {}
result = {}
if config['merge_overview']:
    with open(config['merge_overview'], 'r') as f:
        d = json.load(f)
    empty_table('overview_complete')
    merge_overview_multiprocess(d)
    collect_results('overview_complete')
elif config['merge_changes']:
    with open(config['merge_changes'], 'r') as f:
        d = json.load(f)
    empty_table('changes_complete')
    merge_changes_multiprocess(d)
    collect_results('changes_complete')