import streamlit as st
from streamlit.components.v1 import html

from PIL import Image
import base64
import logging
import validators
import time
import os
import math
from decouple import config
from util import include_css, download_image, save_uploaded_file, replace_values_in_index_html
import json
from SPARQLWrapper import SPARQLWrapper, JSON, POST
from pprint import pprint   
import streamlit as st
import streamlit.components.v1 as components  # Import Streamlit
import pandas as pd
from streamlit_agraph import agraph, Node, Edge, Config
from streamlit_tags import st_tags, st_tags_sidebar
import seaborn as sns

EXPORT_IMAGE_ENDING = "-ascii-art.png"
PAGE_ICON = config('PAGE_ICON')
PAGE_IMAGE = config('PAGE_IMAGE')
GITHUB_REPO = config('GITHUB_REPO')
DESCRIPTION = config('DESCRIPTION').replace("\\n", "\n") % (GITHUB_REPO, GITHUB_REPO + "/issues/new", GITHUB_REPO + "/issues/new")
META_DESCRIPTION = config('META_DESCRIPTION', default=None)

REPLACE_INDEX_HTML_CONTENT = config('REPLACE_INDEX_HTML_CONTENT', default=False, cast=bool)
CANONICAL_URL = config('CANONICAL_URL', default=None)
ADDITIONAL_HTML_HEAD_CONTENT = config('ADDITIONAL_HTML_HEAD_CONTENT', default="")

SOURCE_UPLOAD = "Upload"
SOURCE_DOWNLOAD = "Download"
PAGE_TITLE = "Knowledge Graph Visualizer"
MIN_WIDTH = 10
MAX_WIDTH = 300
RENDER_SCALE_PIXELS = 8
DEFAULT_OUTPUT_WIDTH = 1024
BASIC_NODE_SIZE = 5
SLEEP_TIME = 0.1
START_RESOURCE_COLOR = "#0000FF"

DBPEDIA_ENDPOINT = "http://dbpedia.org/sparql"
WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"

PREFIXES = {
    "dbr": "http://dbpedia.org/resource/",
    "dbo": "http://dbpedia.org/ontology/",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "purl": "http://purl.org/dc/terms/",
    "schema": "http://schema.org/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "xmls": "http://www.w3.org/2001/XMLSchema#",
    "wgs84_pos": "http://www.w3.org/2003/01/geo/wgs84_pos#",
    "prov": "http://www.w3.org/ns/prov#",
    "yago": "http://dbpedia.org/class/yago/",
    "dbp": "http://dbpedia.org/property/",
    "virtrdf": "http://www.openlinksw.com/schemas/virtrdf#",
    "virtrdf-data-formats": "http://www.openlinksw.com/virtrdf-data-formats#",
    "wd": "http://www.wikidata.org/entity/",
    "wds": "http://www.wikidata.org/entity/statement/",
    "wdv": "http://www.wikidata.org/value/>",
    "wdt": "http://www.wikidata.org/prop/direct/",
    "wikibase": "http://wikiba.se/ontology#",
    "p": "http://www.wikidata.org/prop/",
    "ps": "http://www.wikidata.org/prop/statement/",
    "pq": "http://www.wikidata.org/prop/qualifier/",
    "bd": "http://www.bigdata.com/rdf#",
}

width = 60
agree_on_showing_additional_information = True
render_scale_pixels = RENDER_SCALE_PIXELS
number_of_requests = 0
nodes = []
edges = []
palette = sns.color_palette().as_hex()
color_map = {}

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)


REPLACE_INDEX_HTML_CONTENT = True
replace_values_in_index_html(st, REPLACE_INDEX_HTML_CONTENT, 
                             new_title=PAGE_TITLE, 
                             new_meta_description=META_DESCRIPTION, 
                             new_noscript_content=DESCRIPTION, 
                             canonical_url=CANONICAL_URL, 
                             page_icon_with_path=PAGE_ICON,
                             additional_html_head_content=ADDITIONAL_HTML_HEAD_CONTENT + """
<style>
        span.rti--tag {
            color: #fff !important;
            background-color: #000 !important;
        }
</style>
"""
                            )

st.set_page_config(layout="wide", initial_sidebar_state="expanded",
                   page_title=PAGE_TITLE,
                   page_icon=Image.open(PAGE_ICON)
                   )
include_css(st, [
            "css/style_github_ribbon.css",
            "css/style_menu_logo.css", 
            "css/style_logo.css", 
            "css/style_ascii_images.css", 
            "css/style_tabs.css", 
            "css/style_sttags.css"]
)  


with open(PAGE_IMAGE, "rb") as f:
    image_data = base64.b64encode(f.read()).decode("utf-8")
    st.sidebar.markdown(
        f"""
        <div style="display:table;margin-top:-10%;margin-bottom:15%;margin-left:auto;margin-right:auto;text-align:center">
            <a href="{GITHUB_REPO}" title="go to GitHub repository"><img src="data:image/png;base64,{image_data}" class="app_logo"></a>
        </div>
        """,
        unsafe_allow_html=True,
    )

sparql_endpoint = st.sidebar.text_input("SPARQL endpoint:", value=DBPEDIA_ENDPOINT, help="SPARQL endpoint to query, e.g., %s or %s" % (DBPEDIA_ENDPOINT, WIKIDATA_ENDPOINT))

if sparql_endpoint != None and validators.url(sparql_endpoint):
    sparql = SPARQLWrapper(sparql_endpoint)
    st.header(f"Knowledge Graph Visualizer for&nbsp;[{sparql_endpoint}]({sparql_endpoint}) ", help="Used prefixes: \n* " + "\n* ".join([f"`{prefix}: {prefix_url}`" for prefix, prefix_url in PREFIXES.items()]))
else:
    sparql = None
    st.header("Knowledge Graph Visualizer")
    st.info("Please provide a valid SPARQL endpoint, e.g., %s or %s" % (DBPEDIA_ENDPOINT, WIKIDATA_ENDPOINT))
    st.stop()


def execute_query_convert_and_count(sparql, query_string):
    try:
        global number_of_requests
        # number_of_requests += 1
        sparql.setQuery(query_string)
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()
        return results["results"]["bindings"]
    except Exception as e:
        logging.error(e)
        logging.error(query_string)
        st.error(st.code(query_string))
        st.error(e)
        return []


def execute_start_resource_query_convert_and_count(sparql, all_start_values, p_values, p_blocked_values, limit):
    size = 25
    start_values_chunks = [all_start_values[x:x+size] for x in range(0, len(all_start_values), size)]
    
    print("execute_start_resource_query_convert_and_count:" + str(len(all_start_values)) )
    pprint(start_values_chunks, width=160)
    
    results = []
    all_queries = ""
    for start_values,count in zip(start_values_chunks, range(len(start_values_chunks))):
        start_values_sparql = " ".join(["<%s>" % x for x in start_values])
        # select all ingoing and outgoing resources of the start resources
        query_string = """
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX dbr: <http://dbpedia.org/resource/>
            PREFIX dbo: <http://dbpedia.org/ontology/>
            
            SELECT ?s ?p ?o ?direction WHERE {
                {
                    ?s ?p ?o .
                    # filter for start resources
                    VALUES ?s { %s }
                    BIND("outgoing" AS ?direction) # o should be used next
                }
                UNION
                {
                    ?s ?p ?o .
                    # filter for start resources
                    VALUES ?o { %s }
                    BIND("ingoing" AS ?direction) # s should be used next
                }
                # define allowed types of p
                %s 
                
                # define blocked types of p
                %s
            } 
            # LIMIT applied later
            # ORDER randomly
            ORDER BY RAND()
        """ % (start_values_sparql, start_values_sparql, p_values, p_blocked_values)
        print("execute_start_resource_query_convert_and_count:", count, "/", len(start_values_chunks), query_string)
        
        all_queries += query_string
        results_iteration = execute_query_convert_and_count(sparql, query_string)
        results += results_iteration
        
        # stop if we have enough results
        if len(results) >= limit:
            break
        else:
            time.sleep(SLEEP_TIME)

    return results, all_queries


@st.cache_data
def get_data(sparql_endpoint, number_of_results, allowed_properties, blocked_properties, start_resources):
    
    p_values = " ".join(["<%s>" % x for x in allowed_properties])
    if len(allowed_properties) > 0:
        p_values = "VALUES ?p { %s }" % (p_values,)
    else:
        p_values = ""
        
    # filter out blocked properties
    p_blocked_values = "\n".join(["FILTER(STR(?p) != \"%s\")" % x for x in blocked_properties])
    
    # simple query to get all resources if no start resources are given
    if len(start_resources) == 0:
        query_string = """
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX dbr: <http://dbpedia.org/resource/>
            PREFIX dbo: <http://dbpedia.org/ontology/>
            
            SELECT ?s ?p ?o WHERE {
                ?s ?p ?o .
                # define allowed types of p
                %s 
                # define blocked types of p
                %s
            } 
            LIMIT %d
        """ % (p_values, p_blocked_values, number_of_results)
        
        with st.spinner('Wait for it...'):
            with st.expander("SPARQL query (LIMIT %d)" % (number_of_results,), expanded=False):
                st.code(query_string)

        return execute_query_convert_and_count(sparql, query_string)

    else: # start resources are given
        all_query_strings = "" # save all queries for showing it in the expander
        results = [] # save all results
        # iterate over resources until we have enough results
        while number_of_results > len(results):
            results_iteration, query_string = execute_start_resource_query_convert_and_count(sparql, start_resources, p_values, p_blocked_values, number_of_results)

            all_query_strings += query_string
            new_start_resources = []
            
            # collect all ingoing and outgoing resources of the start resources
            for result in results_iteration:
                s = result["s"]["value"]
                o = result["o"]["value"]
                direction = result["direction"]["value"]
                if s not in start_resources and s not in new_start_resources and s not in start_resources and validators.url(s) and direction == "ingoing":
                    new_start_resources.append(s)
                if o not in start_resources and o not in new_start_resources and o not in start_resources and validators.url(o) and direction == "outgoing":
                    new_start_resources.append(o) 
                    
            print("STEP: old_start_resources:", len(start_resources), "results_iteration:", len(results_iteration), "results:", len(results))
            start_resources = new_start_resources.copy()
            results += results_iteration
            print("STEP: new_start_resources:", len(new_start_resources), "results_iteration:", len(results_iteration), "results:", len(results))
            
            if len(new_start_resources) == 0: # stop if no more resources are found
                print("no more NEW start resources found")
                break
            else:
                time.sleep(SLEEP_TIME)

        with st.expander("SPARQL query (LIMIT %d by %d results for the start resources)" % (number_of_results, len(results)), expanded=False):
            st.code(all_query_strings)

        return results[:number_of_results]
        


@st.cache_data
def get_resources(sparql_endpoint, max):
        
        query_string = """
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX dbr: <http://dbpedia.org/resource/>
            
            SELECT DISTINCT ?s WHERE {
                ?s ?p ?o .
            }
            LIMIT %d
        """ % (max,)
        results = execute_query_convert_and_count(sparql, query_string)
        return [x["s"]["value"] for x in results]


@st.cache_data
def get_all_properties(sparql_endpoint):
    
    cleaned_sparql_endpoint = sparql_endpoint.replace(":", "_").replace("/", "_").replace(".", "_")
    cache_filename= "all_properties_" + cleaned_sparql_endpoint + ".json"
    
    print("checking for cache file: " + cache_filename + " ...")
    if os.path.exists(cache_filename):    
        print("loading all properties from cache file: " + cache_filename + " ...")
        with open(cache_filename, "r") as f:
            all_properties = json.load(f)
            return all_properties        
    else:
        print("cache file not found, will create it later with the retrieved results: " + cache_filename + " ...")
    
    page = 0
    all_properties = []
    
    while True:
        # will not work with more with properties that are not defined in the ontology, like rdf:type
        query_string = """
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>   
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX dbr: <http://dbpedia.org/resource/>
            PREFIX dbo: <http://dbpedia.org/ontology/>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            
            SELECT DISTINCT ?property WHERE {
                ?property rdf:type ?type .
                VALUES ?type { rdf:Property owl:DatatypeProperty }
            } 
            LIMIT 10000
            OFFSET %d
        """ % (page * 10000,)
        results = execute_query_convert_and_count(sparql, query_string)
        
        if len(results) == 0:
            break
        else:
            all_properties += [x["property"]["value"] for x in results]
            page += 1
        
        
    # ask N times for properties that are not defined in the ontology, like rdf:type
    for i in range(2):
        query_string = """
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX dbr: <http://dbpedia.org/resource/>
            PREFIX dbo: <http://dbpedia.org/ontology/>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX yago: <http://dbpedia.org/class/yago/>
            
            SELECT DISTINCT ?property WHERE {
                ?s ?property ?o .
            }
            LIMIT 10000
        """
        results = execute_query_convert_and_count(sparql, query_string)
        
        for result in results:
            p = result["property"]["value"]
            if p not in all_properties:
                #print("found new property: " + p)
                all_properties.append(p)
    
    # cache all data in a file
    with open(cache_filename, "w") as f:
        json.dump(all_properties, f)
        print("cache file written: " + cache_filename + " ...")
    
    return all_properties


@st.cache_data
def get_resource_data(sparql_endpoint, uri):
    
    def replace_parenthesis(str):
        return str.replace("(", "\(").replace(")", "\)")
    
    if sparql_endpoint == WIKIDATA_ENDPOINT:
        query_string = """
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX dbr: <http://dbpedia.org/resource/>
            
            SELECT DISTINCT ?p ?p_label ?o
            WHERE {
                <%s> ?p ?o .
                FILTER(!isLiteral(?o) || lang(?o) = "" || langMatches(lang(?o), "EN"))
                BIND(?p AS ?p_label)
            }
            ORDER BY LCASE(?p_label)
        """ % (uri,)
        
    else:
        query_string = """
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX dbr: <http://dbpedia.org/resource/>
            
            SELECT DISTINCT ?p ?p_label ?o
            WHERE {
                <%s> ?p ?o .
                ?p rdfs:label ?p_label .
                FILTER(!isLiteral(?p_label) || lang(?p_label) = "" || langMatches(lang(?p_label), "EN"))
                #BIND (datatype(?o) AS ?dt)
                FILTER(STR(?p) != "http://dbpedia.org/ontology/wikiPageWikiLink")
                FILTER(STR(?p) != "http://dbpedia.org/property/wikiPageUsesTemplate")
                FILTER(STR(?p) != "http://www.w3.org/2002/07/owl#sameAs")
                FILTER(!isLiteral(?o) || lang(?o) = "" || langMatches(lang(?o), "EN"))
                #BIND(STR(?o) AS ?o_v)
            }
            ORDER BY LCASE(?p_label)
        """ % (uri,)
    #print(query_string)
    
    with st.expander("SPARQL query for " + uri.replace("_", "&#95;").replace(":", "\:"), expanded=False):
        st.code(query_string)
    
    results = execute_query_convert_and_count(sparql, query_string)    
    return results


@st.cache_data
def get_dataframe_from_results(resource_data, indegree, outdegree):
    
    def get_property_urls(resource_data):
        for result in resource_data:
            p = result["p"]["value"]
            yield p

    def get_properties(resource_data):
        for result in resource_data:
            p = result["p"]["value"]
            p_label = result["p_label"]["value"]
            #yield "[%s](%s)" % (p_label, p)
            yield p_label
    
    def get_values(resource_data):
        for result in resource_data:
            o = result["o"]["value"]
            yield o
    
    df = pd.DataFrame({
        "property": ["indegree", "outdegree"] + list(get_properties(resource_data)),
        "property_url": ["", ""] + list(get_property_urls(resource_data)),
        "values": [indegree, outdegree] + list(get_values(resource_data))
    })

    return df


@st.cache_data
def get_labels(results):
    resources = []
    for result in results:
        s = result["s"]["value"]
        p = result["p"]["value"]
        o = result["o"]["value"]

        if validators.url(s) and s not in resources:
            resources.append(s)
        if validators.url(o) and o not in resources:
            resources.append(o)
        #if p not in resources:
        #    resources.append(p)


    size = 25
    resources_chunks = [resources[x:x+size] for x in range(0, len(resources), size)]

    results = []
    for resources_chunk in resources_chunks:
        try:
            
            if sparql_endpoint == WIKIDATA_ENDPOINT:
                query_string = """ 
                    # wikidata needs specific query for labels
                    SELECT ?s ?p (?sLabel AS ?o)
                    WHERE {
                        SELECT ?s ?p ?sLabel
                        WHERE 
                        {
                            BIND(?res AS ?s)
                            BIND(<http://www.w3.org/2000/01/rdf-schema#label> AS ?p)
                            BIND(?sLabel AS ?o)
                            
                            VALUES ?res { %s }
                            
                            {
                                SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } 
                                #?prop wikibase:directClaim ?s .
                            }
                        }
                    }
                """ % (" ".join(["<%s>" % x for x in resources_chunk]))
            
            else:
                query_string = """
                    # get labels the standard way
                    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                    PREFIX dbr: <http://dbpedia.org/resource/>
                    PREFIX dbo: <http://dbpedia.org/ontology/>
                    
                    SELECT ?s ?p ?o WHERE {
                        ?s ?p ?o .
                        VALUES ?s { %s }
                        VALUES ?p { rdfs:label }
                        FILTER ( LANG(?o) = "en" )
                    }
                """ % (" ".join(["<%s>" % x for x in resources_chunk]))
                #print("get labels:", query_string)

            results += execute_query_convert_and_count(sparql, query_string)

        except Exception as e:
            st.error(st.code(query_string))
            st.error(e)
    
    return results, resources


def replace_url_by_prefixes(url):
    for prefix, prefix_url in PREFIXES.items():
        if url.startswith(prefix_url):
            return prefix + ":" + url[len(prefix_url):]
    return url


def get_node_size(str):
    node_size = get_node_degree(str) + 1
    # make it proportionally smaller, use log scale
    return round(math.log(node_size * 5, 2))

@st.cache_data
def get_color(str):
    if str == "none":
        return "#000000"
    
    if str not in color_map and len(palette) > 0:
        last_color = palette.pop()
        color_map[str] = last_color
        return color_map[str]
    
    if str in color_map:
        return color_map[str]
    else:
        return "#666666"    


node_color_palette = sns.color_palette(palette='RdYlGn').as_hex()

def get_node_color(str, start_resources):
    
    if str in start_resources:
        return START_RESOURCE_COLOR
    
    if str == "none":
        return "#000000"
    node_degree = get_node_degree(str)
    max_degree = get_max_node_degree()
    
    i = min(round(node_degree / max_degree * (len(node_color_palette) - 1)), (len(node_color_palette) - 1))
    color = node_color_palette[i]
    
    #print("node_degree: %d, max_degree: %d, i: %d, color: %s" % (node_degree, max_degree, i, color))
    
    return color

def get_max_node_degree():
    return max(max(indegree_map.values()), max(outdegree_map.values()))

def get_node_degree(str):
    if str in indegree_map and str in outdegree_map:
        return indegree_map[str] + outdegree_map[str]
    elif str in indegree_map:
        return indegree_map[str]
    elif str in outdegree_map:
        return outdegree_map[str]
    else:
        return 0 # should never happen

def create_help_string_from_list(my_values):
    my_values_copy = my_values.copy()
    random.shuffle(my_values_copy)
    return "Examples: \n* `" + "`\n* `".join(my_values_copy[:25]) + "`"

all_properties = get_all_properties(sparql_endpoint)

import random
all_properties_copy = all_properties.copy()
random.shuffle(all_properties_copy)
st.markdown("""
            <span class="properties_whitelist">Properties whitelist:</span> 
            What properties should be shown (%d available)?""" 
            % (len(all_properties),), help=create_help_string_from_list(all_properties_copy), unsafe_allow_html=True)
whitelist_properties = st_tags(
    key="whitelist_properties",
    label="",
    text='Type here',
    suggestions=all_properties,
    maxtags=-1,
)


st.markdown("""
            <span class="properties_blacklist">Properties blacklist:</span> 
            What properties should *NOT* be shown (%d available)?""" 
            % (len(all_properties),), help=create_help_string_from_list(all_properties_copy), unsafe_allow_html=True)
blacklist_properties = st_tags(
    key="blacklist_properties",
    label="",
    text='Type here',
    suggestions=all_properties,
    maxtags=-1,
)


#start_resources = st.multiselect("What resources should be shown?", get_resources(max=10000))


known_available_resources = get_resources(sparql_endpoint, max=10000)
if known_available_resources == 10000:
    known_available_resources_text = "more than 10000"
else:
    known_available_resources_text = str(len(known_available_resources))
    
st.markdown("""
            <span class="start_resources">What resources (of %s) should be used for the start (will search for properties from these nodes)?</span>""" 
            % (known_available_resources_text, ), help=create_help_string_from_list(known_available_resources), unsafe_allow_html=True)
start_resources = st_tags(
    key="start_resources",
    label="",
    text='Type here',
    suggestions=known_available_resources,
    maxtags=-1    
)


number_of_results = st.sidebar.slider("number of edges",min_value=10, max_value=1000, value=10, step=10)
if number_of_results >= 300:
    st.sidebar.info("Please be patient, this might take a while depending on your browser's computing power.")
layout = st.sidebar.selectbox('layout',['dot','neato','circo','fdp','sfdp'], index=0)
rankdir = st.sidebar.selectbox("rankdir", ['BT', 'TB', 'LR', 'RL'], index=2)
ranksep = st.sidebar.slider("ranksep",min_value=0, max_value=20, value=10)
nodesep = st.sidebar.slider("nodesep",min_value=0, max_value=20, value=5)
nodeSpacing = st.sidebar.slider("nodeSpacing",min_value=50, max_value=500, value=200, step=50)
stabilization = True
fit = True
edgeMinimization = False
#spring_length = st.sidebar.slider("springLength",min_value=0, max_value=500)
solver = st.sidebar.selectbox("solver", ['barnesHut', 'repulsion', 'hierarchicalRepulsion', 'forceAtlas2Based'], index=2)


data = get_data(sparql_endpoint, number_of_results=number_of_results, allowed_properties=whitelist_properties, blocked_properties=blacklist_properties, start_resources=start_resources)
labels, resources = get_labels(data)
indegree_map = {}
outdegree_map = {}
property_counter_map = {}
for result in data:
    s = result["s"]["value"]
    p = result["p"]["value"]
    o = result["o"]["value"]
    
    if s not in outdegree_map:
        outdegree_map[s] = 0
    outdegree_map[s] += 1
    
    if o not in indegree_map:
        indegree_map[o] = 0
    indegree_map[o] += 1

    # count number of properties
    if p not in property_counter_map:
        property_counter_map[p] = 0
    property_counter_map[p] += 1

with st.expander("Number of **nodes: %d**, number of **properties: %d**" % (len(property_counter_map),len(resources)), expanded=False):
    st.dataframe(pd.DataFrame({
        "property": list(property_counter_map.keys()),
        "count": list(property_counter_map.values())
    }).sort_values(by="count", ascending=False))
    #st.toast("""You might use these properties for the whitelist or blacklist.""", icon="💡", )



for result in data + labels:
    # https://github.com/ChrisDelClea/streamlit-agraph/blob/master/streamlit_agraph/node.py#L18
    
    s = result["s"]["value"]
    s_shape = "dot"
    if "s_type" in result:
        s_type = replace_url_by_prefixes(result["s_type"]["value"])
    else:
        s_type = "none"
        
    p = result["p"]["value"]
    
    o = result["o"]["value"]
    if validators.url(o):
        o_label = replace_url_by_prefixes(o)
    else:
        o_label = o[:64] # cut down to 64 characters

    o_shape = "dot"    
    if "o_type" in result:
        o_type = replace_url_by_prefixes(result["o_type"]["value"])
    else:
        o_type = "none"

    if o in start_resources:
        o_shape = "square"
    if s in start_resources:
        s_shape = "square"
    
    if s not in [x.id for x in nodes]:
        nodes.append( Node(id=s, label=replace_url_by_prefixes(s), size=get_node_size(s), color=get_node_color(s, start_resources), shape=s_shape) )
    if o not in [x.id for x in nodes]:
        nodes.append( Node(id=o, label=o_label, size=get_node_size(o), color=get_node_color(o, start_resources), shape=o_shape ) )
    edges.append( Edge(source=s, label=replace_url_by_prefixes(p), target=o, color=get_color(p), arrows_to=True, arrows_from=False, type="CURVE_SMOOTH") )




# https://github.com/ChrisDelClea/streamlit-agraph/blob/master/streamlit_agraph/config.py
config = Config(width="100%",
                height=800,
                directed=True, 
                physics=True,
                solver=solver,
                graphviz_layout=layout,
                graphviz_config={
                    "rankdir": rankdir, 
                    "ranksep": ranksep, 
                    "nodesep": nodesep
                },
                stabilization=stabilization,
                fit=fit,
                edgeMinimization=edgeMinimization,
                nodeSpacing=nodeSpacing,
                node={'labelProperty':'label'},
                hierarchical=False,
                collapsible=True,
                layout={
                    "improvedLayout": True,
                }
                # **kwargs
                )

return_value = agraph(nodes=nodes, edges=edges, config=config)

#st.sidebar.markdown("### Number of executed query for the current visualization: %d" % (number_of_requests,))

print(return_value)

if return_value is not None:    
    try:    
        if validators.url(return_value):
            resource_data = get_resource_data(sparql_endpoint, return_value)
        
            df = get_dataframe_from_results(resource_data, indegree=indegree_map.get(return_value,0), outdegree=outdegree_map.get(return_value,0))
            st.dataframe(df,
                        column_config={
                            "property": st.column_config.TextColumn(),
                            "property_url": st.column_config.LinkColumn(),
                        },
                        width=1000,
                        height=500,
            )
        else:
            st.info("Please click on a resource node to see more information from the knowledge graph.")
    except Exception as e:
        st.error(e)



st.markdown("""
---
Brought to you by the [<img style="height:3ex;border:0" src="https://avatars.githubusercontent.com/u/120292474?s=96&v=4"> WSE research group](https://wse-research.org/) at the [Leipzig University of Applied Sciences](https://www.htwk-leipzig.de/).

See our [GitHub team page](http://wse.technology/) for more projects and tools.
""", unsafe_allow_html=True)

with open("js/change_menu.js", "r") as f:
    javascript = f.read()
    components.html(f"<script style='display:none'>{javascript}</script>")

components.html("""
<script>
github_ribbon = parent.window.document.createElement("div");            
github_ribbon.innerHTML = '<a id="github-fork-ribbon" class="github-fork-ribbon right-bottom" href="%s" target="_blank" data-ribbon="Fork me on GitHub" title="Fork me on GitHub">Fork me on GitHub</a>';
if (parent.window.document.getElementById("github-fork-ribbon") == null) {
    parent.window.document.body.appendChild(github_ribbon.firstChild);
}
</script>
<style>
.rti--container .rti--tag {
    background-color: #FFF;
    color: #000 !important;
    border: 1px solid #000;
}
</style>
""" % (GITHUB_REPO,))
