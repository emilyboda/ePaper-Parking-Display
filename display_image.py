import epd_7_in_5_v3_colour as driver
from PIL import Image,ImageDraw,ImageFont
from upload_to_sheet import *
import time
import datetime
import numpy
import json
import math

#######################################
##### DEFINE SOME THINGS ##############
#######################################

## Give me two pixel -> coord locations for the map you're using for the convertions
# pix: (x, y) -> coord: (lat, lon)
pix1 = (87., 22.)
coord1 = (55.9354974, -70.1333976)
pix2 = (466., 870.)
coord2 = (55.926688, -70.168141)

# geojson file
geojsonfile = '/home/pi/parking/map.geojson'

## where's my house
housecoords = (55.9654274, -78.1433392)

## I need to know what map file you're using (make sure it's exactly the resolution of your display)
mapfile = '/home/pi/parking/map.png'

## set credentials file path and sheet id
credentials_file_path = "/home/pi/parking/" # the file should be named token.pickle 
sheet_id = 'fdjs342874jk23jk32--432n4289fdd4j4h56h' # the id in the sheet URL

#######################################
##### DEFINE SOME FUNCTIONS ###########
#######################################

def optimise_colours(image, threshold=220):
  buffer = numpy.array(image.convert('RGB'))
  red, green = buffer[:, :, 0], buffer[:, :, 1]
  buffer[numpy.logical_and(red <= threshold, green <= threshold)] = [0,0,0] #grey->black
  image = Image.fromarray(buffer)
  return image
  
def coord2pix(pix1, pix2, coord1, coord2, coord):
	x = (coord[1]-coord1[1])*((pix2[0]-pix1[0])/(coord2[1]-coord1[1]))+pix1[0]
	y = (coord[0]-coord1[0])*((pix2[1]-pix1[1])/(coord2[0]-coord1[0]))+pix1[1]
	return (x,y)
	
def pix2coord(pix1, pix2, coord1, coord2, pix):
	lon = (pix[0] - pix1[0])*((coord2[1] - coord1[1])/(pix2[0] - pix1[0]))+coord1[1]
	lat = (pix[1] - pix1[1])*((coord2[0] - coord1[0])/(pix2[1] - pix1[1]))+coord1[0]
	return (lat, lon)
	
def get_slope_intercept(coords):
	coords1, coords2 = coords[0], coords[1]
	m = (coords2[1] - coords1[1])/(coords2[0] - coords1[0])
	b = coords1[1] - m*coords1[0]
	return m, b
	
def dist(point1, point2):
    result = math.sqrt(
        (point2[0] - point1[0])*(point2[0] - point1[0]) +
        (point2[1] - point1[1])*(point2[1] - point1[1])
        )
    return(result)
	
def get_dist_from_line(line, point):
    m1, b1 = get_slope_intercept(line)
    m2 = 1/m1*-1
    b2 = point[1] - m2*point[0]

    x = (b1 - b2)/(m2 - m1)
    y = m1*x+b1
    closestpoint = (x, y)
    acc = dist(point, closestpoint)
    
    return(closestpoint, acc)

def vectorToSegment2D(t, P, A, B):
	return [
			(1 - t) * A[0] + t * B[0] - P[0],
			(1 - t) * A[1] + t * B[1] - P[1]
			]

def sqDiag2D(P):
	return P[0] ** 2 + P[1] ** 2
	
def get_closest_point_from_list(geojsonfile, car_coords):
	with open(geojsonfile) as f:
		roads = json.load(f)
	
	smallest_dist = 10000
	for feature in roads['features']:
		line = [[feature['geometry']['coordinates'][0][1], feature['geometry']['coordinates'][0][0]], 
				[feature['geometry']['coordinates'][1][1], feature['geometry']['coordinates'][1][0]]]
		
		A = (line[0][0], line[0][1])
		B = (line[1][0], line[1][1])
		P = car_coords
		v = [B[0] - A[0], B[1] - A[1]]
		u = [A[0] - P[0], A[1] - P[1]]
		vu = v[0] * u[0] + v[1] * u[1]
		vv = v[0] ** 2 + v[1] ** 2
		t = -vu / vv
		if t >= 0 and t <= 1:
			# if closest is on the line segment, then return this
			test_closest, test_dist = get_dist_from_line(line, car_coords)
		else:
			g0 = sqDiag2D(vectorToSegment2D(0, P, A, B))
			g1 = sqDiag2D(vectorToSegment2D(1, P, A, B))
			if g0 < g1:
				test_closest = A
				test_dist = dist(A, P)
			else:
				test_closest = B
				test_dist = dist(B, P)
		
		if test_dist < smallest_dist:
			smallest_dist = test_dist
			closest_coord = test_closest
			closest_street = feature['properties']['name']
			road_vector = (A, B)
		# print(feature['properties']['name'], test_dist, test_closest)
	return closest_street, smallest_dist, closest_coord, road_vector


#######################################
##### STUFF ABOUT DISPLAY #############
#######################################

epd = driver.EPD()
display_width = driver.EPD_HEIGHT
display_height = driver.EPD_WIDTH

#######################################
##### GET COORD FROM GOOGLE SHEET #####
#######################################
print('initializing google sheet')
service = auth(credentials_file_path)
print('getting car coords from google sheet')
car_loc_str = get_from_sheet(service, sheet_id, 'current', 'B')[0][1].replace(' ', '').split(',')
car_coords = (float(car_loc_str[0]), float(car_loc_str[1]))
print('car is located at coordinates:', car_coords)

#######################################
##### CHECK IF COORD HAS CHANGED ######
#######################################

with open('/home/pi/parking/lastcoords.txt', 'r') as f:
	pastcoords = f.read()

with open('/home/pi/parking/lastmode.txt', 'r') as f:
	pastmode = f.read()

if str(car_coords) != pastcoords:
	print('--> the car location has changed')

	print('saving new car coords to file')
	with open('/home/pi/parking/lastcoords.txt', 'w') as f:
		f.write(str(car_coords))	
		
	print('converting car location to pixels')
	car_pix = coord2pix(pix1, pix2, coord1, coord2, car_coords)
	
	if car_pix[0] < 0 or car_pix[0] > display_width or car_pix[1] < 0 or car_pix[1] > display_height:
		print('--> the car is out of display bounds')
		if pastmode != 'car is off display':
			print('clearing the display since the car was previously on the display')
			print('initializing the screen....')
			epd.init()
			time.sleep(2)
			print('clearing the screen.......')
			epd.Clear()
			time.sleep(2)
			print('putting display to sleep')
			epd.sleep()
			print('writing new mode to file')
			with open('/home/pi/parking/lastmode.txt', 'w') as f:
				f.write('car is off display')
			
			# ADD SOMETHING HERE TO DISPLAY WHEN OFF DISPLAY
	else:
		print('--> the car is on display')
		closest_street, smallest_dist, closest_coord, road_vector = get_closest_point_from_list(geojsonfile, car_coords)
		print('the car is on', closest_street, '. distance:', smallest_dist, 'closest_coord:', closest_coord)
		closest_road_pix = coord2pix(pix1, pix2, coord1, coord2, closest_coord)
		print('the car will be displayed at pixels', closest_road_pix)
		with open('/home/pi/parking/lastmode.txt', 'w') as f:
			f.write('car is on display')
			
		print('initializing the screen....')
		epd.init()
		time.sleep(2)
		print('clearing the screen.......')
		epd.Clear()
		time.sleep(2)
		print('initializing the screen....')
		epd.init()
		time.sleep(2)
		#######################################
		##### DISPLAY MAP ON SCREEN ###########
		#######################################
		
		# CREATE THE MAP IMAGES
		print('building map images')
		color_image = Image.open(mapfile)
		black_image = Image.new('1', (epd.height, epd.width), 255)
		
		# OPTIMIZE COLORS
		#print('optimizing image colors')
		# color_image = optimise_colours(color_image)
		# black_image = optimise_colours(black_image)
		
		draw = ImageDraw.Draw(black_image)
		
		# DRAW MY HOUSE
		house = coord2pix(pix1, pix2, coord1, coord2, housecoords)
		# housew = 10.
		# draw.ellipse([house[0]-housew/2, house[1]-housew/2, house[0]+housew/2, house[1]+housew/2], fill=0, width=1)
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
		draw.ellipse([closest_road_pix[0]-carw/2, closest_road_pix[1]-carw/2, closest_road_pix[0]+carw/2, closest_road_pix[1]+carw/2], fill=0, width=1)
		
		# SAVING MAP IMAGES
		print('saving map images')
		black_image.save('/home/pi/parking/images/'+datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S')+' black.png')
		color_image.save('/home/pi/parking/images/'+datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S')+' color.png')
		
		# DISPLAY MAP IMAGES
		print('displaying the map images....')
		epd.display(epd.getbuffer(black_image),epd.getbuffer(color_image))
		time.sleep(2)
		
		print('putting display to sleep')
		epd.sleep()
		
else:
	print('--> the car location has not changed. nothing will happen')
	


