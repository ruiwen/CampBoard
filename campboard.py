import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.websocket
import tornado.database

import os
import random
import json
import threading
import Queue
import tweepy
from tweepy.models import Status


campboard = {
	'event_tag': '#bcampsg6',
	'additional_tags': [],
	'ws_clients': [],
	'incoming': [],
	'incoming_ws_clients': Queue.Queue()
}

from tornado.options import define, options

define("port", default=8888, help="run on the given port", type=int)
define("mysql_host", default="127.0.0.1:3306", help="blog database host")
define("mysql_database", default="campboard", help="blog database name")
define("mysql_user", default="campboard", help="blog database user")
define("mysql_password", default="campycamp", help="blog database password")

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
			(r"/", MainHandler),
			(r"/echo/", EchoWebSocket),
			(r"/update/", UpdateHandler)
        ]
        settings =  {
        	'debug': True,
            'template_path': os.path.join(os.path.dirname(__file__), "templates"),
            'static_path': os.path.join(os.path.dirname(__file__), "static"),
 			#'xsrf_cookies': True,
 			#'cookie_secret': "12!@#as.dq23/adskjlA1@d33c2t2#25tcf??.43%?1",
        }
        tornado.web.Application.__init__(self, handlers, **settings)

        # Have one global connection to the blog DB across all handlers
        self.db = tornado.database.Connection(
            host=options.mysql_host, database=options.mysql_database,
            user=options.mysql_user, password=options.mysql_password)


class BaseHandler(tornado.web.RequestHandler):
    @property
    def db(self):
        return self.application.db

class MainHandler(BaseHandler):
	def get(self):
		self.render("index.html")

class UpdateHandler(BaseHandler):
	@classmethod
	def get_updates(data):
		pass		

	def get(self):
		# Update all clients
		for i in campboard['ws_clients']:
			i.write_message("Greetings! Thanks for being with us today!")
			i.write_message("There are currently %d clients on board." % len(campboard['ws_clients']))
			i.write_message("Have a good day ahead!")
		self.write("OK")

class EchoWebSocket(tornado.websocket.WebSocketHandler):
	def open(self):
		if self not in campboard['ws_clients']:
			#campboard['incoming_ws_clients'].put_nowait(self)
			campboard['ws_clients'].append(self)

		self.receive_message(self.on_message)

	def on_message(self, message):
		print "Message: " + message
		#self.write_message(unicode(dir(self)))
				
		if "Add Session #bcampsg6" in message:
			for i in campboard['ws_clients']:
				i.write_message(message)
				
		elif "Show clients" in message:
			self.write_message(unicode(campboard['ws_clients']))
			
		elif message == "Close":
			campboard['ws_clients'].remove(self)
		else:
			self.write_message(u"You said: " + message)

		self.receive_message(self.on_message)



class CampBoardStreamListener(tweepy.StreamListener):
	def on_data(self, data):
		print "Got data"
		print data
		Updater.update(data)

	def on_error(self, status_code):
		print 'An error has occured! Status code = %s' % status_code
		return True  # keep stream alive

	def on_timeout(self):
		print 'Snoozing Zzzzzz'


class Updater(object):
	
	incoming = [] # Buffer to hold incoming data bits
	stream = None # To hold the Tweepy Stream
	
	@classmethod
	def start_updating(self, username, password, follow=None, track=None, timeout=None):
		print "Starting updating"
		print "Args: Username: %s Password: %s" % (username, password)
		self.stream = tweepy.Stream(username, password, CampBoardStreamListener(), timeout)
		self.stream.filter(follow, track, True)
		return

	@classmethod
	def update(self,data):
		print "Appending"
		# Stuff data into database
		self.incoming.append(data)
		self._process_data()
		
	@classmethod
	def _process_data(self):
		print "Processing"
		#statuses = [Status.parse(self.stream.api, json.loads(item)) for item in self.incoming if 'in_reply_to_status_id' in item]
		#s = statuses[0]
		statuses = []
		try:
			while True:
				item = self.incoming.pop() # It's gonna throw up someday!
				if "in_reply_to_status_id" in item:
					statuses.append(Status.parse(self.stream.api, json.loads(item)))
				# Ignore anything other than status updates for now
				#else:
				#	statuses.append(json.loads(item))
		except IndexError:
			pass
		
		broadcast = {} # Prepare our broadcast object
		broadcast['total_tweets'] = random.randint(0,1000) # FAKE
		broadcast['unique_tweeters'] = random.randint(0,1000) # FAKE
		
		# Session faking
		broadcast['sessions'] = {}
		broadcast['sessions']['nodejs'] = random.randint(30, 99)
		broadcast['sessions']['distdb'] = random.randint(15, 76)
		broadcast['sessions']['websockets'] = random.randint(24, 83)
		broadcast['sessions']['touchtable'] = random.randint(14, 55)
		
		broadcast['recent_tweets'] = [
			{
				'text': s.text, 'created_at': unicode(s.created_at), 'id': s.id,
				'user': {
					'id': s.user.id,
					'screen_name': s.user.screen_name,
					'profile_image_url': s.user.profile_image_url
				}
			}
			for s in statuses
		
		]
		
		self.ws_broadcast(broadcast)
		
# 		for s in statuses:
# 			if s.text:
# 				self.ws_broadcast("%s tweeted: %s" % (s.author.screen_name, s.text))
# 			else:
# 				self.ws_broadcast(s)
	
	@classmethod
	def ws_broadcast(self, data):
		'''Broadcast data to all connected WebSocket clients'''
			
		print "Broadcasting to %d clients" % (len(campboard['ws_clients']))
		try:
			for i in campboard['ws_clients']:
				print data
				i.write_message(data)
			
		except:
			pass # Fail silently
		



if __name__ == "__main__":
	
	threading.Thread(target=Updater.start_updating, name="update_thread", args=('partyblankone', 'partyon', ['108958644'], ['barcamp'])).start()
	print "Starting server"
	http_server = tornado.httpserver.HTTPServer(Application())
	http_server.listen(options.port)
	tornado.ioloop.IOLoop.instance().start()
	