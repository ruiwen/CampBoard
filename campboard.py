#!/usr/bin/python
# -*- coding: utf-8 -*-

import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.websocket
import tornado.database

import os
import re
import random
import json
import threading
import Queue
import tweepy
from tweepy.models import Status


campboard = {
	'db': None,
	'event_tag': '#bcampsg6',
	'ws_clients': [],
	'ws_channels': {},
	#'incoming': [],
	#'incoming_ws_clients': Queue.Queue(),
	'sessions': ['nodejs', 'distdb', 'hadoop', 'websockets']
}

from tornado.options import define, options

define("port", default=8888, help="run on the given port", type=int)
define("mysql_host", default="127.0.0.1:3306", help="blog database host")
define("mysql_database", default="campboard", help="blog database name")
define("mysql_user", default="campboard", help="blog database user")
define("mysql_password", default="campycamp", help="blog database password")


# Initialise the database connection
campboard['db'] = tornado.database.Connection(
            host=options.mysql_host, database=options.mysql_database,
            user=options.mysql_user, password=options.mysql_password)


class Application(tornado.web.Application):
	def __init__(self):
		handlers = [
			(r"/", MainHandler),
			(r"/echo/", EchoWebSocket),
			(r"/update/", UpdateHandler),
			(r"/session/(\w+)/?", SessionHandler)
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
		self.db = campboard['db']

class BaseHandler(tornado.web.RequestHandler):
    @property
    def db(self):
        return self.application.db

class MainHandler(BaseHandler):
	def get(self):
		# Craft a broadcast object on first load to seed the page with relevant data
		self.render("index.html")


class SessionHandler(BaseHandler):
	def get(self, session):
		
		# Get latest stats from Updater
		session = session.strip()
		stats = Updater.session_stats(session)
		self.render('session.html', session=session, stats=stats)





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
			campboard['ws_clients'].append(self)

		self.write_message(Updater.general_update())
		self.write_message(Updater.recent_tweets())
		self.receive_message(self.on_message)

	def on_message(self, message):
		print "Message: " + message
		#self.write_message(unicode(dir(self)))
		
		try:
			msg = json.loads(message)
			
			# We should have a dict now
			if msg['method'] == 'session_stats':
				if msg['session'] != "":
					stats = Updater.session_stats(msg['session'])
					Updater.ws_broadcast_channel(msg['session'], stats)
			
		except:
			pass

			
		# Legacy
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
	db = campboard['db']
	
	
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
		#self._process_data()
		self.ws_broadcast(self.update_tweets())
		#self.ws_broadcast(self.general_update())
	
	
	@classmethod
	def update_tweets(self):
		print "Updating tweets"

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
		
		
		for s in statuses:
			tags = re.findall("#([\w]+)", s.text) 
			print "Tags: "
			print tags
			self.db.execute("INSERT INTO tweets (id, user_id, screen_name, profile_image_url, created_at, text) VALUES (%s,%s,%s,%s,%s,%s)", s.id, s.user.id, s.user.screen_name, s.user.profile_image_url, s.created_at, s.text)

			# Establish HABTM relationships, tweets with tags
			for t in tags:
				print "Inserting tag: %s" % t
				self.db.execute('''INSERT INTO hashtags (tag) VALUES (%s) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id), tag=%s; 
					INSERT INTO hashtags_tweets (hash_id, tweet_id) VALUES (LAST_INSERT_ID(), %s)''', t, t, s.id)
				
				# Count the votes while we're at it
				if t in campboard['sessions']:
					vote_type = None
					if re.search('\+1', s.text):
						vote_type = "positive"
					elif re.search('\-1', s.text):
						vote_type = "negative"
					
					if vote_type:
						self.db.execute('INSERT INTO session_votes (session, votes) VALUES (%s, 1) ON DUPLICATE KEY UPDATE votes = votes+1', "%s_%s" % (t, vote_type))
		
		broadcast = {}
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
	
		return broadcast
	
	
	
	@classmethod
	def general_update(self):
		print "Stats update	"
		#statuses = [Status.parse(self.stream.api, json.loads(item)) for item in self.incoming if 'in_reply_to_status_id' in item]
		#s = statuses[0]

		broadcast = {} # Prepare our broadcast object		
		
		# Query our db for the relevant info
		res = self.db.query("SELECT COUNT(user_id) as total_tweets, COUNT(DISTINCT user_id) AS unique_tweeters FROM tweets")[0]
		
		broadcast['total_tweets'] = res.total_tweets #random.randint(0,1000) # FAKE
		broadcast['unique_tweeters'] = res.unique_tweeters #random.randint(0,1000) # FAKE
		
		# Session faking
		broadcast['sessions'] = {}
		
		for session in campboard['sessions']:
			#broadcast['sessions'][session] = Updater.sessions_stats(session, 'positive').get('session_positive', 0)
			broadcast['sessions'][session] = self.session_stats(session, 'positive').get('session_positive', random.randint(0,99)) # For FAKE's SAKE!
			
			
		#broadcast['sessions']['nodejs'] = random.randint(30, 99)
		#broadcast['sessions']['distdb'] = random.randint(15, 76)
		#broadcast['sessions']['websockets'] = random.randint(24, 83)
		#broadcast['sessions']['touchtable'] = random.randint(14, 55)
		
		return broadcast


	@classmethod
	def recent_tweets(self, channel=None):
		
		rt = []
		if channel is None:
			rt = self.db.query("SELECT * FROM tweets ORDER BY created_at DESC LIMIT 10")
		else:
			rt = self.db.query('''SELECT * FROM tweets WHERE id IN (
					SELECT tweet_id FROM hashtags_tweets WHERE hash_id IN 
						(SELECT id FROM hashtags WHERE tag=%s)
					) ORDER BY created_at DESC LIMIT 10 ''', channel)
	
		recent_tweets = [
			{
				'text': t.text, 'created_at': unicode(t.created_at), 'id': t.id,
				'user': {
					'id': t.user_id,
					'screen_name': t.screen_name,
					'profile_image_url': t.profile_image_url
				}
			}
			for t in rt
		]
		
		return {"recent_tweets": recent_tweets}
		
	
	@classmethod
	def session_stats(self, session, selector='all'):
	
		session = session.strip()
		broadcast = {}

		if selector in ['positive', 'stats', 'all']:
			session_positive = self.db.query("SELECT COUNT(*) as positive FROM tweets WHERE text LIKE %s", "+1")[0].positive
			broadcast['session_positive'] = session_positive

		if selector in ['negative', 'stats', 'all']:
			session_negative = self.db.query("SELECT COUNT(*) as negative FROM tweets WHERE text LIKE %s", "-1")[0].negative
			broadcast['session_negative'] = session_negative
		

		if selector in ['tweets', 'all']:					
			broadcast['recent_tweets'] = self.recent_tweets(session)
		

		if selector in ['tweetcount', 'stats', 'all']:
			tweet_count = self.db.query('''SELECT COUNT(*) AS tweet_count FROM tweets WHERE id IN (
					SELECT tweet_id FROM hashtags_tweets WHERE hash_id IN 
						(SELECT id FROM hashtags WHERE tag=%s)
					) ORDER BY created_at DESC''', session)[0].tweet_count
			broadcast['tweet_count'] = tweet_count

		return broadcast

	
	@classmethod
	def ws_broadcast_channel(self, channel, data):
		for i in campboard['ws_channels'][channel]:
			i.write_message(data)
			
	
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


# Global application
campboard['application'] = Application()

if __name__ == "__main__":
	
	threading.Thread(target=Updater.start_updating, name="update_thread", args=('partyblankone', 'partyon', ['108958644'], ['barcamp'])).start()
	print "Starting server"
	http_server = tornado.httpserver.HTTPServer(campboard['application'])
	http_server.listen(options.port)
	tornado.ioloop.IOLoop.instance().start()
	