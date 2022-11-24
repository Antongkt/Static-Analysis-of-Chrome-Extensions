import json
import os
import psycopg2
import resource
from tqdm import tqdm
import multiprocessing as mp
from psycopg2 import sql
import traceback
from tldextract import tldextract
import argparse
import ast
from jsoncomment import JsonComment
from jsmin import jsmin
import jstyleson


error_file = "ERROR FILE: \n"


# limits the memory used
# use for safety precautions to not cause freezing
def limit_memory(maxsize):
    """ Limiting the memory usage to maxsize (in bytes), soft limit. """
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (maxsize, hard))

# extracts the scheme part out of a URL, or alternatively return None if there is no scheme
def extract_scheme(url):
    try:
        if url.startswith('file') or url.startswith('ftp') or url.startswith('urn'):
            return None , url    #url is not relevant
        if url.startswith('http://') or url.startswith('https://') or url.startswith("*://"):
            scheme, host = url.split('://', 1)
            return scheme, host
        else:
            return None , url
    except Exception as e:
        traceback.print_exc()
        return None , url

# extracts host and path parts out of a URL, or returns None for either part if it could not be extracted
def extract_host_and_path(url):
    host, path, extracted_host = None, None, None
    try:
        if "/" in url:
            host, path = url.split("/", 1)
        else:
            host = url
            path = None
        try:
            extracted_host = tldextract.extract(host)
        except:
            print("Error while extracting host for:", host)
            extracted_host = None
        return extracted_host, path
    except Exception as e:
        traceback.print_exc()
        return None , url

# given scheme, host, and path outputs the category in which this URL can be assigned to
# the categories are: irrelevant_urls | all_urls | host_wildcard_urls | scheme_path_wildcard_urls | non_wildcard_urls
def get_url_category(scheme, host, path):
    if host.domain == '*':
        if host.subdomain != '' or '*' in host.suffix:   #rule violation, there should be no chars before the wildcard and no more than one wildcard
            return 'irrelevant_urls'
        elif host.suffix == '':
            return 'all_urls'   #wildcard in the host, this is equivalent to all_urls
        else:
            return 'host_wildcard_urls' #this shouldn't happen that a there is a wildcard and then a suffix (e.g. *.com) as per google docu, but we assume it might
    elif '*' in host.suffix: #rule violation, there should be no char before *
        return 'irrelevant_urls'
    elif '*' in host.subdomain:    
        if '*' in host.domain or '*' in host.suffix:    #rule violation, multiple *
            return 'irrelevant_urls'
        else:
            return 'host_wildcard_urls'                 #wildcard in the subdomain e.g. *.google.com is not as powerful as all_urls
    elif (scheme == '*') or ('*' in path):
        return 'scheme_path_wildcard_urls'
    else:
        return 'non_wildcard_urls'

# will process a list of urls, and assign each to a category
# a dictionary with the categorized urls is returned
# if parameter url list is empty it returns an empty dictionary
def preprocess_urls(hosts):
    if (len(hosts) == 0):
        return {}
    host_permissions = {}
    host_permissions['all_urls'] = []
    host_permissions['host_wildcard_urls'] = []
    host_permissions['scheme_path_wildcard_urls'] = []
    host_permissions['non_wildcard_urls'] = []
    host_permissions['irrelevant_urls'] = []
    try:
        for url in hosts:
            if type(url) is str and url not in [
                "BinaryExpression", "MemberExpression", "CallExpression",
                "LogicalExpression", "Identifier", "app", "dns"
            ]:
                if url.startswith("file://") or url.startswith("ws:") or url.startswith("wss:") \
                        or url.startswith("chrome://favicon") or url.startswith("chrome-extension:") \
                        or "127.0.0.1" in url or "localhost" in url:
                    host_permissions['irrelevant_urls'].append(url)
                    continue
                if url in [
                        "*://*/", "*://*/*", "*://*/*/", "*://*/*/*",
                        "*://*/*/*/*", "http://*/*/", "https://*/*/",
                        "http://*/*", "https://*/*", "http://*/", "https://*/",
                        "<all_urls>"
                ]:
                    tmp = host_permissions['all_urls']
                    host_permissions['all_urls'].append(url)
                else:
                    scheme, host, path = "" , "", ""
                    remainder = ''
                    scheme, remainder = extract_scheme(url)
                    if scheme is not None:
                        host, path = extract_host_and_path(remainder)
                        if scheme and host and path is not None:
                            category = get_url_category(scheme, host, path)
                            host_permissions[category].append(url)
                            continue   
                    host_permissions['irrelevant_urls'].append(url)
    except Exception as e:
        traceback.print_exc()
    finally:
        return(host_permissions)


# uses 30 processes to parse the manifest of each version of each id in the dictionary d
# each process parses the manifests of all respective versions of a sepparate id, and stores
# the results for that id in the database table 'overview'
def parse_manifest_multiprocess(d):
    dataset = []
    for item in d.items():
        dataset.append(stringify(item))
    errors = ''
    with mp.Pool(30) as pool:
         for x in tqdm(pool.imap_unordered(parse_manifest_process, dataset), total=len(dataset)):
                errors += str(x)
    with open('../results/error_log_permissions_overview.txt', 'w') as f:
        f.write(errors)


# parse the manifest of each version for this id, store results in the database
def parse_manifest_process(stringified_dict):
    f = json.loads(stringified_dict)
    id, versions = f.popitem()
    errors = ''
    manifest_data = {}
    d = {}
    d['versions'] = {}
    for version in versions:
        d['versions'][version] = {}
        valid = True
        manifest_path = '../extensions/unziped/' + id + '_' + version + '/manifest.json'
        if not os.path.exists(manifest_path):
            valid = False
            errors += 'Manifest does not exist, likely bad zip file: '
            errors += manifest_path
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

        if (valid):
            manifest_version = 2
            d['versions'][version]['valid'] = 1
            if not ('manifest_version' in manifest_data):
                errors += "\n No manifest version for id: "
                errors += manifest_path
                errors += " defaulting to version 2"
                d['versions'][version]['manifest_version'] = manifest_version
            else:
                manifest_version = manifest_data['manifest_version']
                d['versions'][version]['manifest_version'] = manifest_data['manifest_version']
            d['versions'][version]['permissions'] = get_permissions(manifest_data, manifest_version)
            if d['versions'][version]['permissions']['optional_api_permissions']:
                d['versions'][version]['split_permissions'] = 1
            else:
                d['versions'][version]['split_permissions'] = 0
            if d['versions'][version]['permissions']['optional_host_permissions']:
                d['versions'][version]['split_host_permissions'] = 1
            else:
                d['versions'][version]['split_host_permissions'] = 0
            all_urls_flag = 'none'
            if d['versions'][version]['permissions']['host_permissions'] and len(d['versions'][version]['permissions']['host_permissions']['all_urls']) > 1:
                if d['versions'][version]['permissions']['optional_host_permissions'] and len(d['versions'][version]['permissions']['optional_host_permissions']['all_urls']) > 1:
                    all_urls_flag = 'both'
                else:
                    all_urls_flag = 'mandatory'
            elif d['versions'][version]['permissions']['optional_host_permissions'] and len(d['versions'][version]['permissions']['optional_host_permissions']['all_urls']) > 1:
                all_urls_flag = 'optional'
            d['versions'][version]['all_urls_flag'] = all_urls_flag
        else:
            d['versions'][version]['valid'] = 0

    con = psycopg2.connect(
	host = 'localhost',
	database = 'extension_updates',
	user = 'anton',
	password = 'vgJttLSune5ijQfg3ch6ujh4AgLw{nLs7lfJ')
    with con:
        cur = con.cursor()
        json_data = json.dumps(d)
        query = """INSERT INTO permissions_overview (id, info) VALUES (%s, %s::json)"""
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

            




# receives as parameters the dictionary with the manifest data, and the manifest version
# outputs all found permissions as a dictionary with the following keys:
# api_permissions | optional_api_permissions | host_permissions | optional_host_permissions | irrelevant_permissions
def get_permissions(data, mv):
    permissions = {}
    api_permissions = []
    host_permissions = {}
    optional_api_permissions = []
    optional_host_permissions = {}
    irrelevant_permissions = []     #e.g. app permissions, invalid permissions (e.g. api permissions inside the host permission key in mv3), etc. Filter these out
    urls = []
    optional_urls = []

    if mv == 2:
        if 'permissions' in data:
            for permission in data['permissions']:
                if permission in API_PERMISSIONS:   #this is an API permission
                    api_permissions.append(permission)
                elif permission in OUTDATED_PERMISSIONS:        #this is an outdated API permissions, therefore irrelevant
                    irrelevant_permissions.append(permission)
                else:
                    urls.append(permission)                     #this is either a host permission, or something irrelevant / invalid. Filter urls to find valid host permissions later
        if 'optional_permissions' in data:          
            for permission in data['optional_permissions']:     #same steps as for mandatory permissions, differenchiate in groups
                if permission in API_PERMISSIONS:
                    optional_api_permissions.append(permission)
                elif permission in OUTDATED_PERMISSIONS:
                    irrelevant_permissions.append(permission)
                else:
                    optional_urls.append(permission)
    elif mv == 3:
        if 'permissions' in data:
            for permission in data['permissions']:
                if permission in API_PERMISSIONS:           #this is an API permission
                    api_permissions.append(permission)
                else:
                    irrelevant_permissions.append(permission)   #this is either some deprecated API permission, or some invalid api / host permission (either due to syntax or typo etc)
        if 'optional_permissions' in data:
            for permission in data['optional_permissions']:     #same steps as for mandatory permissions, differenchiate in groups
                if permission in API_PERMISSIONS:
                    optional_api_permissions.append(permission)
                else:
                    optional_urls.append(permission)
        if 'host_permissions' in data:
            for permission in data['host_permissions']:
                urls.append(permission)
        if 'optional_host_permissions' in data:
            for permission in data['optional_host_permissions']:
                optional_urls.append(permission)

    # We have to process host permissions, and sepparate the urls into categories:
    # 1. all_urls category
    # 2. match pattern category with wildcard in the host (does not imply all_urls, e.g. *.google.com, *.com etc)
    # 3. match pattern category with wildcard in the scheme or in the path
    # 4. non match pattern url category, which contains valid urls
    # 4. invalid url category (urls is syntactically false / violates the rules from developer.chrome). This are irrelevant because chrome does not take them into account
    host_permissions = preprocess_urls(urls)
    optional_host_permissions = preprocess_urls(optional_urls)

    # put all gathered data into a dictionary as a result
    permissions['api_permissions'] = api_permissions
    permissions['optional_api_permissions'] = optional_api_permissions
    permissions['irrelevant_permissions'] = irrelevant_permissions
    permissions['host_permissions'] = host_permissions
    permissions['optional_host_permissions'] = optional_host_permissions
    return permissions


# compares two sets of permissions, and detects changes
# api permission changes include addition / deletetion and moving of permissions from optional to mandatory and vice versa
# host permission changes are described by one of the following tags:
# uncertain | all_urls_added | all_urls_removed | host_wildcard_added | host_wildcard_removed | url_count_increase | url_count_decrease | irrelevant
def compare_versions(permissions_before, permissions_after):
    result = {}
    api_permissions_change = 1
    api_permissions_before = set(permissions_before['api_permissions'])
    api_permissions_after = set(permissions_after['api_permissions'])
    optional_api_permissions_before = set(permissions_before['optional_api_permissions'])
    optional_api_permissions_after = set(permissions_after['optional_api_permissions'])

    if (api_permissions_after == api_permissions_before) and (optional_api_permissions_before == optional_api_permissions_after):
        api_permissions_change = 0
    else:
        before_total = api_permissions_before.union(optional_api_permissions_before)
        after_total = api_permissions_after.union(optional_api_permissions_after)
        new_api_permissions = api_permissions_after.difference(before_total)
        new_optional_api_permissions = optional_api_permissions_after.difference(before_total)
        deletted_api_permissions = api_permissions_before.difference(after_total)
        deletted_optional_api_permissions = optional_api_permissions_before.difference(after_total)
        #detect permissions that might have just been moved
        moved_to_mandatory = set()
        moved_to_optional = set()

        tmp1 = new_api_permissions.union(api_permissions_before)
        tmp2 = api_permissions_after.difference(tmp1)
        if len(tmp2) > 0:
            for element in tmp2:
                if element in optional_api_permissions_before and element not in optional_api_permissions_after:
                    moved_to_mandatory.add(element)
                elif element in optional_api_permissions_before and element in optional_api_permissions_after:
                    new_api_permissions.add(element)
        
        tmp1 = new_optional_api_permissions.union(optional_api_permissions_before)
        tmp2 = optional_api_permissions_after.difference(tmp1)
        if  len(tmp2) > 0:
            for element in tmp2:
                if element in api_permissions_before and element not in api_permissions_after:
                    moved_to_optional.add(element)
                elif element in api_permissions_before and element in api_permissions_after:
                    new_optional_api_permissions.add(element)

        tmp1 = api_permissions_after.union(deletted_api_permissions)
        tmp2 = api_permissions_before.difference(tmp1)
        if len (tmp2) > 0:
            for element in tmp2:
                if element not in optional_api_permissions_before and element in optional_api_permissions_after:
                    moved_to_optional.add(element)
                elif element in optional_api_permissions_before and element in optional_api_permissions_after:
                    deletted_api_permissions.add(element)

        tmp1 = optional_api_permissions_after.union(deletted_optional_api_permissions)
        tmp2 = optional_api_permissions_before.difference(tmp1)
        if len (tmp2) > 0:
            for element in tmp2:
                if element not in api_permissions_before and element in api_permissions_after:
                    moved_to_mandatory.add(element)
                elif element in api_permissions_before and element in api_permissions_after:
                    deletted_optional_api_permissions.add(element)
        

    result['api_permissions_change'] = api_permissions_change
    if api_permissions_change:
        result['api_permission_change_details'] = {}
        result['api_permission_change_details']['new_api_permissions'] = list(new_api_permissions)
        result['api_permission_change_details']['deleted_api_permissions'] = list(deletted_api_permissions)
        result['api_permission_change_details']['new_optional_api_permissions'] = list(new_optional_api_permissions)
        result['api_permission_change_details']['deleted_optional_api_permissions'] = list(deletted_optional_api_permissions)
        result['api_permission_change_details']['moved_to_optional'] = list(moved_to_optional)
        result['api_permission_change_details']['moved_to_mandatory'] = list(moved_to_mandatory)
    result['host_permission_change'] = compare_host_permissions(permissions_before['host_permissions'], permissions_after['host_permissions'])
    result['optional_host_permission_change'] = compare_host_permissions(permissions_before['optional_host_permissions'], permissions_after['optional_host_permissions'])
    return result



# compares host permissions to derive the tag which describes the change in host permissions
def compare_host_permissions(permissions_before, permissions_after):
    change = ''
    if not (permissions_before) and not (permissions_after):
        change = 'irrelevant'
    elif (permissions_before) and not (permissions_after):
        if len(permissions_before['all_urls']) > 0:
            change = 'all_urls_deleted'
        elif len(permissions_before['host_wildcard_urls']):
            change = 'host_wildcard_deletted'
        else:
            change = 'url_count_decrease'
    elif not (permissions_before) and (permissions_after):
        if len(permissions_after['all_urls']) > 0:
            change = 'all_urls_added'
        elif len(permissions_after['host_wildcard_urls']):
            change = 'host_wildcard_added'
        else:
            change = 'url_count_increase'        
    else:
        if (len(permissions_before['all_urls']) > 0) and (len(permissions_after['all_urls']) > 0):
            change = 'irrelevant'
        elif (len(permissions_before['all_urls']) > 0) and (len(permissions_after['all_urls']) == 0):
            change = 'all_urls_deleted'
        elif (len(permissions_before['all_urls']) == 0) and (len(permissions_after['all_urls']) > 0):
            change = 'all_urls_added'
        else:
            if (permissions_before):
                non_host_wildcards_before = set(permissions_before['scheme_path_wildcard_urls'])
                host_wildcards_before = set(permissions_before['host_wildcard_urls'])
                regular_urls_before = set(permissions_before['non_wildcard_urls'])
            else:
                non_host_wildcards_before = set()
                host_wildcards_before = set()
                regular_urls_before = set()
            if (permissions_after):
                non_host_wildcards_after = set(permissions_after['scheme_path_wildcard_urls'])
                host_wildcards_after = set(permissions_after['host_wildcard_urls'])
                regular_urls_after = set(permissions_after['non_wildcard_urls'])
            else:
                non_host_wildcards_after = set()
                host_wildcards_after = set()
                regular_urls_after = set()
            if (non_host_wildcards_after == non_host_wildcards_before) and (host_wildcards_before == host_wildcards_after) and (regular_urls_after == regular_urls_before):
                change = 'irrelevant'
            else:
                wildcards_before = host_wildcards_before.union(non_host_wildcards_before)
                wildcards_after = host_wildcards_after.union(non_host_wildcards_after)
                if not wildcards_before and not wildcards_after:
                    if len(regular_urls_before) == len(regular_urls_after):
                        change = 'irrelevant'
                    elif len(regular_urls_before) > len(regular_urls_after):
                        change = 'url_count_decrease'
                    elif len(regular_urls_before) < len(regular_urls_after):
                        change = 'url_count_increase'
                elif wildcards_before and not wildcards_after:
                    if len(host_wildcards_before) > 0:
                        change = 'host_wildcard_deleted'
                    elif regular_urls_before.issuperset(regular_urls_after):
                        change = 'url_count_decrease'
                    else:
                        change = 'uncertain'
                elif wildcards_after and not wildcards_before:
                    if len(host_wildcards_after) > 0:
                        change = 'host_wildcard_added'
                    elif regular_urls_before.issubset(regular_urls_after):
                        change = 'url_count_increase'
                    else:
                        change = 'uncertain'
                elif wildcards_after and wildcards_before:
                    if wildcards_before == wildcards_after:
                        if regular_urls_before == regular_urls_after:
                            change = 'irrelevant'
                        elif regular_urls_before.issubset(regular_urls_after) and len(regular_urls_before) < len(regular_urls_after):
                            change = 'url_count_increase'
                        elif regular_urls_after.issubset(regular_urls_before) and len(regular_urls_before) > len(regular_urls_after):
                            change = 'url_count_decrease'
                        else:
                            change = 'uncertain'
                    elif wildcards_before.issubset(wildcards_after):
                        if (host_wildcards_before).issubset(host_wildcards_after) and len(host_wildcards_before) < len(host_wildcards_after):
                            change = 'host_wildcard_added'  #additional subdomain wildcard was added
                        elif (regular_urls_before.issubset(regular_urls_after)):    # both scheme/path wildcard as well as regular urls were added
                            change = 'url_count_increase'
                        else:
                            change = 'uncertain'
                    elif wildcards_before.issuperset(wildcards_after):
                        if (host_wildcards_before).issuperset(host_wildcards_after) and len(host_wildcards_before) > len(host_wildcards_after):
                            change = 'host_wildcard_deleted'  #additional subdomain wildcard was added
                        elif (regular_urls_before.issuperset(regular_urls_after)):  # both scheme/path wildcard as well as regular urls were deletted
                            change = 'url_count_decrease'
                        else:
                            change = 'uncertain'
                    else:
                        change = 'uncertain'
    return change
                        

# for the given id, detect all permission changes across all versions
# for each id, first data is querried from the table 'overview', which contains the permissions for each version
# store results in database table 'changes'
def compare_changes_process(stringified_dict):
    f = json.loads(stringified_dict)
    id, versions = f.popitem()
    errors = ''
    result = {}
    data = {}
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

        
    data = cur.fetchall()[0][0]   #list of tuples is returned
    
    result['updates'] = {}
    validUpdates = []
    for i in range(len(versions)):
        if data['versions'][versions[i]]['valid'] == 1:
            validUpdates.append(versions[i])
    updates_with_change = 0
    
    if (len(validUpdates) >= 2):        #need at least 2 valid entries to check changes
        indexA = 0
        indexB = 1

        result['start_version'] = validUpdates[indexA]
        result['start_all_permissions'] = list(set(data['versions'][validUpdates[indexA]]['permissions']['api_permissions']).union(set(data['versions'][validUpdates[indexA]]['permissions']['optional_api_permissions'])))
        all_urls_flag = 'none'
        if data['versions'][validUpdates[indexA]]['permissions']['host_permissions'] and len(data['versions'][validUpdates[indexA]]['permissions']['host_permissions']['all_urls']) > 1:
            if data['versions'][validUpdates[indexA]]['permissions']['optional_host_permissions'] and len(data['versions'][validUpdates[indexA]]['permissions']['optional_host_permissions']['all_urls']) > 1:
                all_urls_flag = 'both'
            else:
                all_urls_flag = 'mandatory'
        elif data['versions'][validUpdates[indexA]]['permissions']['optional_host_permissions'] and len(data['versions'][validUpdates[indexA]]['permissions']['optional_host_permissions']['all_urls']) > 1:
            all_urls_flag = 'optional'
        result['start_all_urls_flag'] = all_urls_flag


        while (indexB < len(validUpdates)):
            current_version = validUpdates[indexB]
            previous_version = validUpdates[indexA]
            print('COMPARING VERSIONS: ' + current_version + ' AND ' + previous_version)
            
            d = compare_versions(data['versions'][previous_version]['permissions'], data['versions'][current_version]['permissions'])
            if ( d['host_permission_change'] != 'irrelevant') or (d['optional_host_permission_change'] != 'irrelevant') or (d['api_permissions_change'] == 1):
                updates_with_change += 1
                result['updates'][current_version] = d
                result['updates'][current_version]['all_requested_permissions'] = list(set(data['versions'][current_version]['permissions']['api_permissions']).union(set(data['versions'][current_version]['permissions']['optional_api_permissions'])))
                result['updates'][current_version]['previous_version'] = previous_version
                all_urls_flag = 'none'
                if data['versions'][current_version]['permissions']['host_permissions'] and len(data['versions'][current_version]['permissions']['host_permissions']['all_urls']) > 1:
                    if data['versions'][current_version]['permissions']['optional_host_permissions'] and len(data['versions'][current_version]['permissions']['optional_host_permissions']['all_urls']) > 1:
                        all_urls_flag = 'both'
                    else:
                        all_urls_flag = 'mandatory'
                elif data['versions'][current_version]['permissions']['optional_host_permissions'] and len(data['versions'][current_version]['permissions']['optional_host_permissions']['all_urls']) > 1:
                    all_urls_flag = 'optional'
                result['updates'][current_version]['all_urls_flag'] = all_urls_flag



            
            indexB += 1
            indexA += 1
    

        total_versions = len(versions)
        valid_versions = len(validUpdates)
        jsondata = json.dumps(result)
        with con:
            cur = con.cursor()
            query = "INSERT INTO permission_changes (id, permission_info, total_versions, valid_versions, permission_change_updates) VALUES (%s, %s::json, %s, %s, %s)"
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



def compare_versions_new(permissions_before, permissions_after):
    result = {}
    api_permissions_change = 1
    api_permissions_before = set(permissions_before['api_permissions'])
    api_permissions_after = set(permissions_after['api_permissions'])
    optional_api_permissions_before = set(permissions_before['optional_api_permissions'])
    optional_api_permissions_after = set(permissions_after['optional_api_permissions'])
    all_permissions_before = api_permissions_before.union(optional_api_permissions_before)
    all_permissions_after = api_permissions_after.union(optional_api_permissions_after)
    new_requested_permissions = set()
    no_longer_requested_permissions = set()

    if all_permissions_after == all_permissions_before:
        api_permissions_change = 0
    else:
        new_requested_permissions = all_permissions_after.difference(all_permissions_before)
        no_longer_requested_permissions = all_permissions_before.difference(all_permissions_after)
    result['host_permission_change'] = compare_host_permissions(permissions_before['host_permissions'], permissions_after['host_permissions'])
    result['optional_host_permission_change'] = compare_host_permissions(permissions_before['optional_host_permissions'], permissions_after['optional_host_permissions'])
    result['api_permission_change'] = api_permissions_change
    if (api_permissions_change == 1):
        result['new_requested_permissions'] = new_requested_permissions
        result['no_longer_requested_permissions'] = no_longer_requested_permissions
    return result
    





# call 30 processes to detect changes in permissions for all extension ids, 
# each process works on a sepparate id
def compare_changes_multiprocess(d):
    dataset = []
    for item in d.items():
        dataset.append(stringify(item))
    errors = ''
    with mp.Pool(30) as pool:
         for x in tqdm(pool.imap_unordered(compare_changes_process, dataset), total=len(dataset)):
                errors += str(x)
    with open('../results/error_log_permission_changes.txt', 'w') as f:
        f.write(errors)



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
                d[row[0]]['updates_with_change'] = row[4]
    
    with open('../results/results_' + table + '.json', 'w') as f:
        json.dump(d, f, indent=4)

def stringify(x):
    id = x[0]
    versions = x[1]
    d = {}
    d[id] = versions
    return json.dumps(d)      

API_PERMISSIONS = ["activeTab", "alarms", "background", "bookmarks", "browsingData", "certificateProvider", "clipboardRead", 

"clipboardWrite", "contentSettings", "contextMenus", "cookies", "debugger", "declarativeContent", 

"declarativeNetRequest", "declarativeNetRequestFeedback", "declarativeWebRequest", "desktopCapture", 

"documentScan", "downloads", "enterprise.deviceAttributes", "enterprise.hardwarePlatform", 

"enterprise.networkingAttributes", "enterprise.platformKeys", "experimental", "fileBrowserHandler", 

"fileSystemProvider", "fontSettings", "gcm", "geolocation", "history", "identity", "idle", "loginState", 

"management", "nativeMessaging", "notifications", "pageCapture", "platformKeys", "power", "printerProvider", 

"printing", "printingMetrics", "privacy", "processes", "proxy", "scripting", "search", "sessions", 

"signedInDevices", "storage", "system.cpu", "system.display", "system.memory", "system.storage", "tabCapture", 

"tabGroups", "tabs", "topSites", "tts", "ttsEngine", "unlimitedStorage", "vpnProvider", "wallpaper", 

"webNavigation", "webRequest", "webRequestBlocking"]



OUTDATED_PERMISSIONS = ['audioCapture', 'fileSystem', 'serial', 'usb', 'videoCapture', 'syncFileSystem', 
'system.network', 'app.window.fullscreen.overrideEsc', 'mediaGalleries', 'hid', 'app.window.fullscreen', 
'network.config', 'u2fDevices', 'identity.email', 'metricsPrivate', 'usbDevices', 'mediaGalleries', 'fileSystem', 
'commands', 'browser', 'location', 'fileBrowserProvider', 'webview', 'fullscreen', 'overrideEscFullscreen', 'downloads.open', 
'downloads.shelf', 'streamsPrivate', 'windows', 'activetab', 'active_tab', 'ActiveTab', 'activeTab>', 'activeTabs', 'audioCapture', 
'fileSystem', 'mediaGalleries', 'serial', 'syncFileSystem', 'usb', 'videoCapture', 'system.network', 'hid', 'app.window.fullscreen', 
'app.window.fullscreen.overrideEsc', 'u2fDevices', 'fileSystem', 'app', 'dns', 'socket']


limit_memory(20*10**9)  # Limiting the memory usage to 20GB
parser = argparse.ArgumentParser(description="This script is used to parse manifests of extensions and collect data about permissions (and changes thereof) between versions.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("-parse_manifest", type=str, help='parse manifests and put collected data in the database. NOTE: manifests must be unziped already!')
parser.add_argument("-compare_changes", type=str, help='analyze data from parse_manifest to detect changes in permissions between versions. NOTE: -parse_manifest must be used first!')







args = parser.parse_args()
config = vars(args)
d = {}
result = {}
if config['parse_manifest']:
    with open(config['parse_manifest'], 'r') as f:
        d = json.load(f)
    empty_table('permissions_overview')
    parse_manifest_multiprocess(d)
    collect_results('permissions_overview')
elif config['compare_changes']:
    with open(config['compare_changes'], 'r') as f:
        d = json.load(f)
    empty_table('permission_changes')
    compare_changes_multiprocess(d)
    collect_results('permission_changes')
    


