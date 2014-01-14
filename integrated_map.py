import urllib
from xml.dom import minidom
import re
import json
import numpy
import pickle
import time
import shapefile
from json import dumps
import csv

"""
NAME
     Analytics: Map Generator

PURPOSE
     Generate a geoJSON database containing coordinates for census tracts with associated demographic and student info. Can be plotted with analytics_map.js.

STATUS
     Operational
     
RUN
     python -i analytics_mapgen.py
     >> diction = make_addresses(address_file) [OR diction = import_coords("save.p")]
     >> main(j, ct_ref, address_file, q, diction)
     
OTHER INPUTS
     Listed under Paths

OUTPUTS
     out.json
     - ["features"][i]["geometry"]["coordinates"]

RUN NOTES
     make_addresses relies on interfacing with the Google Maps API, which limits querries to ~1,500 per day. If you hope to plot more students than that, it requires spreading out your querries over multiple days by querrying, and then saving the resulting dictionary, and then feeding that to the make_addresses fuction. 
    
LOG
    02/01/2014: Operational Version Tested

CONTACT
    Ben Horowitz (Yale University)
    - Benjamin.a.Horowitz@yale.edu
    - Horowitz.Ben@gmail.com
"""

## Paths
# Note: geoJSON can be gotten from shape files via http://techslides.com/demos/mapping/shapefile-geojson-converter.html

csv = './ACS_12_5YR_DP05/ACS_12_5YR_DP05_with_ann.csv'
j = json.load(open('./CT_CensusTract.geojson'))
address_file = open("addresses_Yale","rb")
q = json.load(open('./towns.geojson'))

def initialize_towns(q):
    for i in range(0,173):
        q["features"][i]["geometry"]["bounding"]=boundingBox(q["features"][i]["geometry"]["coordinates"])
    return q

def getAddressCoords(address):
    # Thanks Jojo!!
    j = json.load(urllib.urlopen(
        "http://maps.googleapis.com/maps/api/geocode/json?"
        + "address=%s&sensor=false" % address))
    latlng = j['results'][0]['geometry']['location']
    return (latlng['lat'], latlng['lng'])

def getCensusBlock((lat,lon)):
    url = 'http://data.fcc.gov/api/block/find?latitude=' +str(lat)+'&longitude=' +str(lon) +'&showall=false'
    dom = minidom.parse(urllib.urlopen(url))
    for node in dom.getElementsByTagName('Block'):
        x = node.toxml()
    x = re.findall(r'"(.*?)"', x)
    return x

def students(p10,p15):
    return p10/2 + p15/2

def parseCensusDemographics(csv):
    l = numpy.loadtxt(open(csv,"rb"),delimiter=",", usecols = (2,5,25,29,129,133,157,265), skiprows=1, dtype = 'str')
    # 25 (10-14), 29 (15-19), 5 (total pop), 129 (white), 133 (black), 157 (asian), 265 (hispanic)
    CT_ref = {}
    for i in range(0,l.shape[0]-1):
        if i==0:
            CenTract = l[i][0]
        else:
            CenTract = re.findall(r'[-+]?[0-9]*\.?[0-9]+.', l[i][0])
        #currently records racial demographics in case you want an "under-represented minority stat"
        pall = l[i][1]
        p10 = l[i][2]
        p15 = l[i][3]
        pw = l[i][4]
        pa = l[i][5]
        ph = l[i][6]
        CT_ref[CenTract[0]]=(pall,p10,p15,pw,pa,ph)
    return CT_ref
        
def pointPoly(x,y,poly):
    n = len(poly)
    inside = False
    p1x,p1y = poly[0]
    for i in range(n+1):
        p2x,p2y = poly[i % n]
        if y > min(p1y,p2y):
            if y <= max(p1y,p2y):
                if x <= max(p1x,p2x):
                    if p1y != p2y:
                        xints = (y-p1y)*(p2x-p1x)/(p2y-p1y)+p1x
                    if p1x == p2x or x <= xints:
                        inside = not inside
        p1x,p1y = p2x,p2y
    return inside

def cpPoly(poly):
    polyN = numpy.array(poly)
    x = polyN[:,0].mean()
    y = polyN[:,1].mean()
    return (x,y)

def convert_l(l):
    k = numpy.array(l)
    k = numpy.array(k[0])
    if k.shape[0]<3:
        k = numpy.array(k[0])
    return k

def boundingBox(polygon):
    #Finds bounding box of each census tract to speed up PiP algorithm.
    k = numpy.array(polygon)
    k = numpy.array(k[0])
    if k.shape[0]<3:
        k = numpy.array(k[0])
   
    min_lat = k[:,0].min()
    max_lat = k[:,0].max()
    min_lon = k[:,1].min()
    max_lon = k[:,1].max()
    return (min_lat,min_lon,max_lat,max_lon)

def get_coords(add,diction):
    #Interfaces with google API to get coordinates. Google Maps API limits calls per second and calls per 24 hour period (~1,500 calls).
    for f,line in enumerate(add):
        if line in diction:
            continue
        time.sleep(0.15)
        try:
            print f
            diction[line] = getAddressCoords(line)
        except:
            print "error with ", line
    return diction

def save_coords(diction):
    diction = pickle.save("save.p", diction )
    return

def import_coords(pickle_name):
    diction = pickle.load( open( pickle_name, "rb") )
    return diction

def allocate_students(j,add,CT_ref,diction):
    #allocates students to individual census tracts.
    for f,line in enumerate(add):
      flag = 0
      if line in diction:         
        (lon,lat) = diction[line]
        for i in range(1,len(CT_ref)-1):
            (min_lat,min_lon,max_lat,max_lon) = j["features"][i]["geometry"]["bounding"] # (min_lat,min_lon,max_lat,max_lon)
            #print (min_lat,min_lon,max_lat,max_lon), lat, lon #(-72.432851999999997, 41.255398, -72.347426999999996, 41.342337000000001) 41.5952734 -72.6978515
            if lat<max_lat and lat>min_lat and lon<max_lon and lon>min_lon:
                #print (min_lat,min_lon,max_lat,max_lon), lat, lon, i
                if pointPoly(lat,lon,convert_l(j["features"][i]["geometry"]["coordinates"])):
                    j["features"][i]["properties"]["STUDENTS"] += 1
                    flag = 1
            else:
                continue
      if flag == 0:
          print line
    return j

def allocate_towns(j,q):
    #allocate each census tract to a town based on coordinates. Removes water-only census tracts.
    water = []
    for l in range(0,len(j["features"])-2):
        if j["features"][l] in j["features"]:
            if j["features"][l]["properties"]["ALAND"] == 0:
                print "DEAD MAN WALKES!", j["features"][l]["properties"]["NAME"]
                water.append(l)
        j["features"][l]["properties"]["TOWN_NAME"] = "NONE"
        flag = 0
        (lat,lon) = cpPoly(convert_l(j["features"][l]["geometry"]["coordinates"]))
        for i in range(0,len(q["features"])-1):
            (min_lat,min_lon,max_lat,max_lon) = q["features"][i]["geometry"]["bounding"] # (min_lat,min_lon,max_lat,max_lon)
            if lat<max_lat and lat>min_lat and lon<max_lon and lon>min_lon:
                if pointPoly(lat,lon,convert_l(q["features"][i]["geometry"]["coordinates"])):
                    j["features"][l]["properties"]["TOWN_NAME"] = q["features"][i]["properties"]["NAMELSAD10"]
                    flag = 1
            else:
                continue
        if flag == 0:
            print l
    water.reverse()
    for w in water:
        print "deleting", j["features"][w]["properties"]["NAME"]
        del j["features"][w]
    return j

def clean_addresses(address_file):
    # Removes duplicate users using their name, could be altered to remove based on name and matching address.
    reader=csv.reader(open("addresses_Yale","rb"),delimiter=',')
    x=list(reader)
    result=numpy.array(x).astype('str')
    k = []
    add = []
    for jj in result:
        name = jj[2] 
        if name not in k:
            k.append(name)
            add.append(jj[1])
    return add

def initialize_json(CT_ref,j):
    for i in range(0,len(CT_ref)-1):
        name = j["features"][i]["properties"]["NAME"]
        if name in CT_ref:
            j["features"][i]["properties"]["DEMO"] = CT_ref[name]
        else:
            print name, i
        j["features"][i]["geometry"]["bounding"] = boundingBox(j["features"][i]["geometry"]["coordinates"])
        j["features"][i]["properties"]["STUDENTS"]=0
    return j

def make_addresses(address_file, diction = {}):
    diction = get_coords(add,diction)
    save_coords(diction)
    return diction

def main(j, ct_ref, address_file, q, diction):
    # Main function call
    add = clean_addresses(address_file)
    j_init = initialize_json(ct_ref,j)
    q = initialize_towns(q)
    j = allocate_students(j_init,add,ct_ref,diction)
    j_final = allocate_towns(j,q)
    json.dump(j_final, open('out.json', 'w'))

ct_ref = parseCensusDemographics(csv)




