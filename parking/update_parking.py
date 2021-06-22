import epd_7_in_5_v3_colour as driver
from PIL import Image,ImageDraw,ImageFont
from upload_to_sheet import *
import time
import datetime
import numpy
import json
from math import sin, cos, sqrt, atan2, radians
import pytz
import requests
import shutil
import re
from inky_image import Inkyimage as Images

with open('settings.json', 'r') as f:	# open the settings file
	settings = json.load(f)

#######################################
##### DEFINE SOME FUNCTIONS ###########
#######################################

def dist_coords(home, coords):
	R = 6373.0
	lat1 = radians(home[0])
	lon1 = radians(home[1])
	lat2 = radians(coords[0])
	lon2 = radians(coords[1])
	
	dlonlon = lon2 - lon1
	dlatlon = 0
	alon = sin(dlatlon / 2)**2 + cos(lat2) * cos(lat2) * sin(dlonlon / 2)**2
	clon = 2 * atan2(sqrt(alon), sqrt(1 - alon))
	londistance = R * clon * 1000
	if lon1>lon2:
		londistance = londistance * -1
	
	dlonlat = 0
	dlatlat = lat2 - lat1
	alat = sin(dlatlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlonlat / 2)**2
	clat = 2 * atan2(sqrt(alat), sqrt(1 - alat))
	latdistance = R * clat * 1000
	if lat1<lat2:
		latdistance = latdistance*-1
	return londistance, latdistance
	
def coord2pix(settings, coord):								# converts from coordinates to pixels
	pix_settings = re.findall("[\d.-]+,[\d.-]+,[\d.-]+,[\d.-]+", settings["mapbox request url"])[0].split(",")
	lat, lon, zoom = float(pix_settings[1]), float(pix_settings[0]), float(pix_settings[2])
	resolution = 78271.484 * cos(radians(lat)) / (2.0 ** zoom) #meters/pixel
	xm, ym = dist_coords((lat, lon), coord)
	xp, yp = xm / resolution + 528.0/2, ym / resolution + 880.0/2
	return (xp,yp)

def snap_to_road(car_coords, key):							# uses the google maps snap to road api to move the car's coordinates onto the nearest road
	lat = car_coords[0]
	lon = car_coords[1]
	coords_str = str(lat)+","+str(lon)
	r = requests.get('https://roads.googleapis.com/v1/snapToRoads?path='+coords_str+'&interpolate=false&key='+key)
	closest_coord = (r.json()['snappedPoints'][0]['location']['latitude'], r.json()['snappedPoints'][0]['location']['longitude'])
	return closest_coord
	
def init_screen():											# initializes the waveshare display
	print('initializing the screen....')					# this must be run to clear before displaying anything new
	epd.init()
	time.sleep(10)
	print('clearing the screen.......')
	epd.Clear()
	time.sleep(10)
	print('initializing the screen....')
	epd.init()
	time.sleep(10)

def display_map_images(cim,bim,color_image,black_image):	# displays map images (or not, if the "testing" flag is set to "yes")
	print('saving map images')
	black_image.save(settings['home directory']+'map black.png')
	color_image.save(settings['home directory']+'map color.png')
	
	# DISPLAY MAP IMAGES
	if settings["testing"] == "no":
		init_screen()
		print('displaying the map images....')
		epd.display(epd.getbuffer(bim), epd.getbuffer(cim))
		time.sleep(10)

		print('putting display to sleep')
		epd.sleep()

def make_map_out_of_bounds():								# makes the map image if the car is OUT OF BOUNDS
	# CREATE THE MAP IMAGES

	# print('building map images')
	color_image = Image.open(settings["home directory"]+'map.png')
	black_image = Image.new('1', (epd.height, epd.width), 255)
	
	# flip the images
	cim = color_image.rotate(180, expand=True)
	bim = black_image.rotate(180, expand=True)
	
	display_map_images(cim,bim,color_image,black_image)

	settings['last_mode'] = 'car is off display'

def make_map_in_bounds():									# makes the map image if the car is IN BOUNDS
	print('building map images')
	color_image = Image.open(settings["home directory"]+'map.png')
	black_image = Image.new('1', (epd.height, epd.width), 255)
	
	draw = ImageDraw.Draw(black_image)
	draw_color = ImageDraw.Draw(color_image)

	# DRAW MY HOUSE
	house = coord2pix(settings, settings["house coords"])
	hw = 15.
	A = (house[0]-hw/2, house[1]-hw/2)
	B = (house[0]+hw/2, house[1]+hw/2)
	C = (house[0], house[1] - hw*4/3)
	D = (house[0] - 3*hw/4, house[1] - hw/2)
	E = (house[0] + 3*hw/4, house[1] - hw/2)
	draw.rectangle((A, B), fill=0, width = 1)
	draw.polygon((C, D, E), fill=0)
	
	# DRAW THE CAR
	carw = 10.
	draw.ellipse([	closest_road_pix[0]-carw/2,
					closest_road_pix[1]-carw/2, 
					closest_road_pix[0]+carw/2, 
					closest_road_pix[1]+carw/2
					], fill=0, width=1)
	
	# flip the images
	cim = color_image.rotate(180, expand=True)
	bim = black_image.rotate(180, expand=True)
	
	display_map_images(cim,bim,color_image,black_image)
	
	settings['last_mode'] = 'car is on display'

def pull_new_image():										# this pulls a new image from mapbox when requested
	print('pulling new image...')
	r = requests.get(settings["mapbox request url"], stream=True)
	if r.status_code == 200:
		with open(settings['home directory']+"map.png", 'wb') as f:
			r.raw.decode_content = True
			shutil.copyfileobj(r.raw, f)
		im = Image.open(settings['home directory']+'map.png').convert('RGB')
		im.save(settings['home directory']+'map.png')
	else:
		print('!!! there was an issue getting the new mapbox image. Did you put in the right API key?')

#######################################
##### STUFF ABOUT DISPLAY #############
#######################################
# imports important stuff about the display

epd = driver.EPD()
display_width = driver.EPD_HEIGHT
display_height = driver.EPD_WIDTH

#######################################
##### GET COORD FROM GOOGLE SHEET #####
#######################################

print('initializing google sheet')
credentials_file_path = settings['home directory']
sheet_id = settings["sheet_id"]
service = auth(credentials_file_path)

print('getting car coords')
from_sheet = get_from_sheet(service, sheet_id, 'current', 'C')
car_loc_str = from_sheet[0][1].replace(' ', '').split(',')
car_coords = (float(car_loc_str[0]), float(car_loc_str[1]))

print('car located at', car_coords)
car_ts = from_sheet[0][2]
car_ts_dt = datetime.datetime.utcfromtimestamp(int(car_ts)).replace(tzinfo=pytz.utc).astimezone(pytz.timezone('America/New_York'))
car_ts_day = car_ts_dt.strftime("%A")

#######################################
##### PULL NEW IMAGE IF NECESSARY #####
#######################################

need_to_update = 0

if settings['update mapbox image?'] == "yes":
	pull_new_image()
	settings['update mapbox image?'] = "no"
	print('set need_to_update flag')
	need_to_update = 1

#######################################
## DETERMINE WHAT TO SHOW ON SCREEN ###
#######################################

if settings['testing'] == "yes":								# this is a little work around so that when I'm testing the screen, it will always update
	settings['last_coords'] = '(1, 1)'
	print('--> in testing mode')

if str(car_coords) != settings['last_coords']:					# this determines if the car's location has changed since we last checked
	print('--> car location has changed')

	settings['last_coords'] = str(car_coords)					# saves new car coords to file
	car_pix = coord2pix(settings, car_coords)					# converts the car's pixels to coordinates
	
	if car_pix[0] < 0 or car_pix[0] > display_width or car_pix[1] < 0 or car_pix[1] > display_height:	
																# this determines if the cars new location is within the bounds of the screen
		# The car location has changed, but it's out of bounds
		print('--> car is out of display bounds')
		if settings['last_mode'] != 'car is off display':
			make_map_out_of_bounds()
			
	else:
		# The car location has changed, and it's on the display
		print('--> car is on display')
		closest_coord = snap_to_road(car_coords, settings["google maps api key"])	# snap the coordinate to a nearby road
		closest_road_pix = coord2pix(settings, closest_coord)						# convert the car's coord to a road
		make_map_in_bounds()
	print('set need_to_update flag')
	need_to_update = 1
		
else:
	print('--> car location has not changed. nothing will happen')

#####################################
# NEED TO SAVE NEW SETTINGS.JSON? ###
#####################################

if need_to_update == 1:
	with open('settings.json', 'w') as outfile:					# update the last_mode and last_coords if they've changed
		json.dump(settings,outfile)
	print('updated settings')
