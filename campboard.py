import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.websocket

import json
import threading
import Queue
import tweepy
from tweepy.models import Status

settings = {
	'debug': True,
}

campboard = {
	'event_tag': '#bcampsg6',
	'additional_tags': [],
	'ws_clients': [],
	'incoming': [],
	'incoming_ws_clients': Queue.Queue()
}


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
				else:
					statuses.append(json.loads(item))
		except IndexError:
			pass
		
		for s in statuses:
			if s.text:
				self.ws_broadcast("%s tweeted: %s" % (s.author.screen_name, s.text))
			else:
				self.ws_broadcast(s)
	
	@classmethod
	def ws_broadcast(self, data):
		'''Broadcast data to all connected WebSocket clients'''
		print "Retrieving Queue'd WebSocket clients"
		#while not campboard['incoming_ws_clients'].empty():
		#	try:
		#		c = campboard['incoming_ws_clients'].get_nowait()
		#		if c not in campboard['ws_clients']:
		#			campboard['ws_clients'].append(c)
		#		campboard['incoming_ws_clients'].task_done()
		#	except RuntimeError:
		#		# The Queue is probably empty
		#		pass
			
		print "Broadcasting to %d clients" % (len(campboard['ws_clients']))
		try:
			for i in campboard['ws_clients']:
				print data
				i.write_message(data)
			
		except:
			pass # Fail silently
		


class MainHandler(tornado.web.RequestHandler):
	def get(self):
		#self.write("Hello, world")
		self.render("templates/index.html")

class UpdateHandler(tornado.web.RequestHandler):
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



application = tornado.web.Application([
	(r"/", MainHandler),
	(r"/echo/", EchoWebSocket),
	(r"/update/", UpdateHandler)
], **settings)

if __name__ == "__main__":
	#Updater.start_updating('partyblankone', 'partyon', ['108958644'], ['barcamp'])
	threading.Thread(target=Updater.start_updating, name="update_thread", args=('partyblankone', 'partyon', ['108958644'], ['barcamp'])).start()
	#stream = tweepy.Stream('partyblanktwo', 'partyon', CampBoardStreamListener(), None)
	#stream.filter(['108958644'], ['barcamp'], True)

	print "Starting server"
	http_server = tornado.httpserver.HTTPServer(application)
	http_server.listen(8888)
	tornado.ioloop.IOLoop.instance().start()
	#Updater.start_updating('partyblankone', 'partyon', 'barcamp', '108958644')
	#Updater.start_updating('partyblankone', 'partyon', 'barcamp', '108958936')
	