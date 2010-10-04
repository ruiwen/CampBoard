#!/usr/bin/python
# -*- coding: utf-8 -*-

import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.websocket
import tornado.database
import tornado.escape

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
	'sessions': []
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
			(r"/campsocket/", CampboardSocket),
			(r"/session/(\w+)/?", SessionHandler),
			(r"/poll/?", PollHandler),
			(r"/admin/?", AdminHandler)
		]
		settings =  {
			'debug': True,
			'template_path': os.path.join(os.path.dirname(__file__), "templates"),
			'static_path': os.path.join(os.path.dirname(__file__), "static"),
			#'xsrf_cookies': True,
			'cookie_secret': "2kljq34@#41wedljasxC?+@#+DSWq	2#_!@#()FDM09q34kmndfo",
		}
		tornado.web.Application.__init__(self, handlers, **settings)
	
	    # Have one global connection to the blog DB across all handlers
		self.db = campboard['db']
		
		# Setup sessions from the database
		campboard['sessions'] = [row['name'] for row in self.db.query('''SELECT name FROM sessions''')]
		print campboard['sessions']
		

class BaseHandler(tornado.web.RequestHandler):
    @property
    def db(self):
        return self.application.db

	@property
	def current_user(self):
		return self.get_secure_cookie("user")


class MainHandler(BaseHandler):
	def get(self):
		print "Main"
		# Craft a broadcast object on first load to seed the page with relevant data
		stats = Updater.general_update()
		stats['recent_tweets'] = Updater.recent_tweets()
		self.render("index.html", stats=stats)


class SessionHandler(BaseHandler):
	def get(self, session):
		print "Session %s" % session
		# Get latest stats from Updater
		session = session.strip()
		stats = Updater.session_stats(session)
		self.render('session.html', session=session, stats=stats)

class PollHandler(BaseHandler):
	def get(self):
		print "GET: %s" % self.request.body
		#print unicode(self.request.headers['Referer'])
		self.write({"a":1})
		
		
	def post(self):
		print "POST: %s" % self.request.body
		if "Register: " in self.request.body:
			session_match = re.search('/session/(?P<session>\w+)', self.request.body)
			if session_match:
				channel = session_match.group('session')
				
				self.write({"a":1})
			else:
				broadcast = {}
				broadcast.update(Updater.general_update())
				#rt = Updater.recent_tweets()
				#rt.reverse()
				#broadcast.update({"recent_tweets": rt})
				
				self.write(tornado.escape.json_encode(broadcast))
		else:
			self.write({"a":3})



class AdminHandler(BaseHandler):
	def get(self):
		user = self.get_secure_cookie('user')
		if user and user == 'campmin':			
			self.render("admin.html", sessions=campboard['sessions'])
		else:
			self.render("admin-unauth.html")
		
	def post(self):
		if self.get_argument("adpass") == 'campilicious':
			self.set_secure_cookie('user', 'campmin')
			self.redirect('/admin/')
		else:
			self.redirect('/')

		
class CampboardSocket(tornado.websocket.WebSocketHandler):

	def open(self):
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
			
			
			if msg['method'] == 'session_add':
				Updater.session_add(msg['data'])
				
			
			if msg['method'] == 'session_remove':
				Updater.session_remove(msg['data'])
				
			
			if msg['method'] == 'broadcast_message':
				channel = msg.get('channel', None)			
				Updater.broadcast_message(msg['data'], channel)

					
		except Exception as e:
			print "Message parse failed: %s" % (unicode(e))
			pass

		
		if "Register: " in message:
			print message
			session_match = re.search('/session/(?P<session>\w+)', message)
			if session_match:
				channel = session_match.group('session')
				print "Adding to channel: %s" % channel
				if not campboard['ws_channels'].has_key(channel):
					campboard['ws_channels'][channel] = []
				
				if self not in campboard['ws_channels'][channel]:
					campboard['ws_channels'][channel].append(self)
				

			print "Adding to normal client list"
			# We add all clients to the general list anyway so that everyone gets broadcasts
			if self not in campboard['ws_clients']:
				print "Adding to client list"
				campboard['ws_clients'].append(self)
			
					
				self.write_message(Updater.general_update())
				rt = Updater.recent_tweets()
				rt.reverse()
				self.write_message({"recent_tweets": rt})
				
		
		if message == "Close":
			if self in campboard['ws_clients']:
				campboard['ws_clients'].remove(self)
			
			for channel in campboard['ws_channels']:
				if self in campboard['ws_channels'][channel]:
					campboard['ws_channels'][channel].remove(self)

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
		rts = self.update_tweets()
		self.ws_broadcast(rts['general'])
		self.ws_broadcast(self.general_update())
		
		# Session update
		for s in campboard['sessions']:
			self.ws_broadcast_channel(s, self.session_stats(s, 'stats'))
			if rts['channels'].has_key(s):
				self.ws_broadcast_channel(s, rts['channels'][s])
	
	
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
		
		broadcast = {}
		broadcast['general'] = {}
		broadcast['channels'] = {}
				
		for s in statuses:
			tags = re.findall("#([\w]+)(?iu)", s.text) # Case-insensitive, Unicode matching
			print "Tags: "
			print tags
			self.db.execute("INSERT INTO tweets (id, user_id, screen_name, profile_image_url, created_at, text) VALUES (%s,%s,%s,%s,%s,%s)", s.id, s.user.id, s.user.screen_name, s.user.profile_image_url, s.created_at, s.text)

			# Establish HABTM relationships, tweets with tags
			for t in tags:
				t = t.lower() # Force all to lowercase
				print "Inserting tag: %s" % t
				self.db.execute('''INSERT INTO hashtags (tag) VALUES (%s) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id), tag=%s; 
					INSERT INTO hashtags_tweets (hash_id, tweet_id) VALUES (LAST_INSERT_ID(), %s)''', t, t, s.id)
				
				# Count the votes while we're at it
				if t in campboard['sessions']:
					
					# Attach the tweet to the broadcast channel
					if not broadcast['channels'].has_key(t):
						broadcast['channels'][t] = {}
					
					broadcast['channels'][t]['recent_tweets'] = []
					broadcast['channels'][t]['recent_tweets'].append(
						{
							'text': s.text, 'created_at': unicode(s.created_at), 'id': s.id,
							'user': {
								'id': s.user.id,
								'screen_name': s.user.screen_name,
								'profile_image_url': s.user.profile_image_url
							}				
						}
					)
			
					vote_type = None
					if re.search('\+1', s.text):
						vote_type = "positive"
					elif re.search('\-1', s.text):
						vote_type = "negative"
					
					if vote_type:
						self.db.execute('INSERT INTO session_votes (session, votes) VALUES (%s, 1) ON DUPLICATE KEY UPDATE votes = votes+1', "%s_%s" % (t, vote_type))
				
		

		broadcast['general']['recent_tweets'] = [
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
			broadcast['sessions'][session] = self.session_votes(session).get('cumulative', 0)
				
		broadcast['sessions_number'] = len(campboard['sessions'])
		return broadcast


	@classmethod
	def recent_tweets(self, channel=None, since=0, limit=10):
		
		rt = []
		if channel is None:
			rt = self.db.query("SELECT SQL_CALC_FOUND_ROWS * FROM tweets WHERE id > %s ORDER BY created_at DESC LIMIT %s", since, limit)
		else:
			channel = channel.lower()
			rt = self.db.query('''SELECT SQL_CALC_FOUND_ROWS * FROM tweets WHERE id IN (
					SELECT tweet_id FROM hashtags_tweets WHERE hash_id IN 
						(SELECT id FROM hashtags WHERE tag=%s)
					)  AND id > %s ORDER BY created_at DESC LIMIT %s''', channel, since, limit)
	
		recent_tweets = [
			{
				'text': unicode(t.text), 'created_at': unicode(t.created_at), 'id': t.id,
				'user': {
					'id': t.user_id,
					'screen_name': t.screen_name,
					'profile_image_url': t.profile_image_url
				}
			}
			for t in rt
		]

		#return {"recent_tweets": recent_tweets}
		return recent_tweets
	
	
	@classmethod
	def session_votes(self, session, vote='all'):
		'''Returns Tweets for session matching criteria: 'positive' – '+1', 'negative' – '-1', or 'all'/'stats' for both'''
		
		votes = {}
		
# 		if vote in ['positive', 'stats', 'all']:
# 			res = self.db.query('SELECT votes FROM session_votes WHERE session=%s', '%s_positive' % session)
# 			if res:
# 				votes['positive'] = res[0].votes
# 			else:
# 				votes['positive'] = 0
# 		
# 		if vote in ['negative', 'stats', 'all']:
# 			res = self.db.query('SELECT votes FROM session_votes WHERE session=%s', '%s_negative' % session)
# 			if res:
# 				votes['negative'] = res[0].votes
# 			else:
# 				votes['negative'] = 0

		res = self.db.query("SELECT (SELECT votes FROM session_votes WHERE session = %s) AS positive, (SELECT votes FROM session_votes WHERE session = %s) AS negative", "%s_positive" % session, "%s_negative" % session)

		if res:
			votes['positive'] = res[0].positive or 0
			votes['negative'] = res[0].negative or 0
			votes['cumulative'] = votes['positive'] - votes['negative']
		else:
			votes['positive'] = votes['negative'] = 0

		return votes
		
	
	@classmethod
	def session_stats(self, session, selector='all'):
	
		session = session.strip()
		broadcast = {}
		
		broadcast['channel'] = session

# 		if selector in ['positive', 'stats', 'all']:
# 			session_positive = self.db.query("SELECT COUNT(*) as positive FROM tweets WHERE text LIKE %s", "+1")[0].positive
# 			broadcast['session_positive'] = session_positive
# 
# 		if selector in ['negative', 'stats', 'all']:
# 			session_negative = self.db.query("SELECT COUNT(*) as negative FROM tweets WHERE text LIKE %s", "-1")[0].negative
# 			broadcast['session_negative'] = session_negative
		
		if selector in ['positive', 'negative', 'stats', 'all']:
			broadcast['votes'] = self.session_votes(session, selector)
		

		if selector in ['tweets', 'all']:					
			broadcast['recent_tweets'] = self.recent_tweets(session)
		

		if selector in ['tweetcount', 'stats', 'all']:
			tweet_count = self.db.query('''SELECT COUNT(*) AS tweet_count FROM tweets WHERE id IN (
							SELECT tweet_id FROM hashtags_tweets WHERE hash_id IN
								(SELECT id FROM hashtags WHERE tag=%s)
							) ORDER BY created_at DESC''', session)[0].tweet_count
			
			#self.db.query("SELECT FOUND_ROWS() AS tweet_count")[0].tweet_count # Requires SQL_CALC_FOUND_ROWS() to be used in immediate previous SQL query
			
			broadcast['tweet_count'] = tweet_count

		return broadcast

	
	@classmethod
	def session_add(self, sess):
		campboard['sessions'].append(sess)
		print unicode(campboard['sessions'])
		self.db.execute('''INSERT INTO sessions (name) VALUES (%s) ON DUPLICATE KEY UPDATE name=%s''' , sess, sess)
		self.ws_broadcast(self.general_update())

	
	@classmethod
	def session_remove(self, sess):
		campboard['sessions'].remove(sess)
		print unicode(campboard['sessions'])
		gen = self.general_update()		
		gen['sessions'][sess] = "DEL" # Set DEL to indicate removal
		gen['sessions_number'] = len(campboard['sessions'])		
		self.db.execute('''DELETE FROM sessions WHERE name=%s''' , sess)		
		self.ws_broadcast(gen)
		
	
	@classmethod
	def broadcast_message(self, message, channel=None):
		'''Broadcasts a message to either all clients, or clients on a specific channel'''
		print "Broadcast message"
		if channel is None or channel == 'all':
			self.ws_broadcast({"broadcast_message": message})
		else:
			self.ws_broadcast_channel(channel, {"broadcast_message": message, "channel": channel})
	
	
	@classmethod
	def ws_broadcast_channel(self, channel, data):
		if campboard['ws_channels'].has_key(channel):
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
	
	threading.Thread(target=Updater.start_updating, name="update_thread", args=('partyblankone', 'partyon', ['108958644'], ['campboardtest'])).start()
	print "Starting server"
	http_server = tornado.httpserver.HTTPServer(campboard['application'])
	http_server.listen(options.port)
	tornado.ioloop.IOLoop.instance().start()
	