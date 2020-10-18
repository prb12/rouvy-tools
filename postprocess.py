#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
import time
import fnmatch
import os
import subprocess
import sys
import gpxpy
import srtm
import folium

parser = argparse.ArgumentParser(
         description='Postprocess GoPro MP4 files into GPX files.')
parser.add_argument('-v', '--verbose', action='store_true', default=False,
                    help='Verbose output')

# Useful docs:
# https://docs.python.org/3/library/subprocess.html

def format_time(time: datetime.datetime) -> str:
    offset = time.utcoffset()
    if not offset or offset == 0:
        tz = 'Z'
    else:
        tz = time.strftime('%z')
    if time.microsecond:
        ms = time.strftime('.%f')[:4]  # Miliseconds only!
    else:
        ms = ''
    return ''.join((time.strftime('%Y-%m-%dT%H:%M:%S'), ms, tz))

# Monkey-patch the format_time function for writing GPX files...
gpxpy.gpxfield.format_time = format_time

def showtree(root: str):
    for directory, subdir_list, file_list in os.walk(root):
        print('Directory:', directory)
        for name in subdir_list:
            print('Subdirectory:', name)
        for name in file_list:
            print('File:', name)
        print()

def shell(cmdline:str) -> str:
    ret = subprocess.run('echo %CD%', shell=True, capture_output=True, text=True)
    return ret.stdout

def find_time_errors(gpx, remove=False):
    for trk in gpx.tracks:
        for trkseg in trk.segments:
            time_errors = []
            last_time = -1
            for p, i in trkseg.walk():
                # print(f"#{i} {p}")
                if p.time == last_time:
                    print(f"*** Time error @{p.time} point #{i}")
                    time_errors.append(i)
                last_time = p.time
            #trkseg.remove_point(n)
            if time_errors and remove:
                print(f"Removing time errors: {time_errors}")
                time_errors.reverse()
                for i in time_errors:
                    del trkseg.points[i]

def overlayGPX(gpx, zoom):
    '''
    overlay a gpx route on top of an OSM map using Folium
    some portions of this function were adapted
    from this post: https://stackoverflow.com/questions/54455657/
    how-can-i-plot-a-map-using-latitude-and-longitude-data-in-python-highlight-few
    '''
    points = []
    for track in gpx.tracks:
        for segment in track.segments:        
            for point in segment.points:
                points.append(tuple([point.latitude, point.longitude]))
    latitude = sum(p[0] for p in points)/len(points)
    longitude = sum(p[1] for p in points)/len(points)
    myMap = folium.Map(location=[latitude,longitude],zoom_start=zoom)
    folium.PolyLine(points, color="red", weight=2.5, opacity=1).add_to(myMap)
    myMap.add_child(folium.LayerControl())
    return (myMap)
                
def main(argv):
    # print(argv)
    if len(argv) < 3:
        return
    indir = argv[1]
    outdir = argv[2]

    # Sanity check current dir
    print(shell('echo %CD%'))
    
    # Find all the MP4 files to process
    mp4 = fnmatch.filter(os.listdir(indir), '*.mp4')
 
    # Split the filenames into the video number and segment number
    vidsegs = [(fn[4:], fn[:4]) for fn in mp4]
    # Sort into the order they were created.
    vidsegs.sort()
    mp4 = [seg+vid for (vid, seg) in vidsegs]
    print(f"Processing in order: {mp4}")

    # Init the elevation model
    elevation_data = srtm.get_data()
    
    # return
    for fn in mp4:
        basename = fn.split('.')[0]
        path = os.path.join(indir, fn)
        print(f"Processing {path}")

        if False:
            # Show metadata tags with their tag names (not the human descriptions)
            ret = subprocess.run(['exiftool.exe', '-s', path],
                                check=True, capture_output=True, text=True)
            print(ret.stdout)
    
        # Run exiftool to generate a raw GPX file
        print('Extracting GPS data with exiftool...')
        ret = subprocess.run(['exiftool.exe', '-p', 'gpxfixed.fmt', '-ee', '-progress', path],
                             check=True, capture_output=True, text=True)
        gpx_text = ret.stdout
        
        # Parse into gpxpy 
        print('Parsing GPX output...')
        gpx = gpxpy.parse(gpx_text)
        
        find_time_errors(gpx, remove=True)
        
        #break
        
        print('Smoothing horizontal...')
        # See also remove_extremes flag...
        gpx.smooth(vertical=False, horizontal=True)
            
        print('Fixing elevations...')
        elevation_data.add_elevations(gpx, only_missing=False, smooth=True)
                                
        print("Smoothing vertical...")
        gpx.smooth(vertical=True, horizontal=False)
        
        # Try gpx.simplify?
        # Simplify uses the Ramer-Douglas-Peucker algorithm: 
        # http://en.wikipedia.org/wiki/Ramer-Douglas-Peucker_algorithm
        # PBAR: It's actualy quite good! - but probably makes it harder to edit the 
        # video/GPS because we want frequent GPS points close to iframes.
        if False:
            gpx.simplify(max_distance=1)
        
        # Print some stats?
        ud = gpx.get_uphill_downhill()
        print(ud)
        md = gpx.get_moving_data()
        print(md)
        
        map_obj = overlayGPX(gpx, 14)
        map_fn = os.path.join(outdir, basename+'_map.html') 
        print(f'Writing {map_fn}')
        map_obj.save(outfile=map_fn)
        continue
    
        gpx_fn = os.path.join(outdir, basename+'.GPX')        
        print(f'Writing {gpx_fn}')
        with open(gpx_fn, 'w') as gpxfile:
            gpxfile.write(gpx.to_xml())
            
        # break

if __name__ == '__main__':
    main(sys.argv)
