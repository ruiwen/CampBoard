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
	'event_tag': 'campboardtest',
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

		rt = Updater.recent_tweets()
		if rt:
			# Set cookie for last tweet id
			self.set_cookie('last_tweet_id', unicode(rt[0]['id']))
			stats.update({"recent_tweets": rt})
		else:
			stats['recent_tweets'] = []

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
		
		session_match = re.search('/session/(?P<session>\w+)', self.request.headers['Referer'])
				
		if session_match:
			channel = session_match.group('session')
			channel_poll = Updater.session_stats(channel, 'stats')
			
			last_tweet_id = self.get_cookie('last_tweet_id')
			rt = Updater.recent_tweets(channel, last_tweet_id)			
			if rt:
				# Set cookie for last tweet id
				self.set_cookie('last_tweet_id', unicode(rt[0]['id']))
				rt.reverse()
				channel_poll.update({'recent_tweets': rt})
			else:
				channel_poll['recent_tweets'] = []
			
			self.write(channel_poll)
			
		else:
			general_poll = {}
			general_poll.update(Updater.general_update()) # This line is ridiculous

			last_tweet_id = self.get_cookie('last_tweet_id')
			rt = Updater.recent_tweets(None, last_tweet_id)
			if rt:			
				# Set cookie for last tweet id
				self.set_cookie('last_tweet_id', unicode(rt[0]['id']))
				rt.reverse()
				general_poll.update({"recent_tweets": rt}) # Reverse the tweet list, since we add from the top in JS
			else:
				general_poll['recent_tweets'] = []
			
			self.write(general_poll)
		
		
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
			self.write({})


class AdminHandler(BaseHandler):
	def get(self):
		user = self.get_secure_cookie('user')
		if user and user == 'campmin':			
			stats = Updater.general_update()
			self.render("admin.html", stats=stats)
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
			
			channel = 'main' # Default to the main page channel
			if session_match:
				channel = session_match.group('session')

			print "Adding to channel: %s" % channel
			if not campboard['ws_channels'].has_key(channel):
				campboard['ws_channels'][channel] = []
			
			if self not in campboard['ws_channels'][channel]:
				campboard['ws_channels'][channel].append(self)
				

			if self not in campboard['ws_clients']:
				print "Adding to client list"
				campboard['ws_clients'].append(self)			
 				gen_update = Updater.general_update()

				self.write_message(gen_update)
				
		
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

		general_broadcast = {}
		general_broadcast.update(rts['general']) # recent_tweets array
		general_broadcast.update(self.general_update())
		self.ws_broadcast_channel('main', general_broadcast)
		
		# Session update
		for s in campboard['sessions']:
			channel_broadcast = {}
			channel_broadcast.update(self.session_stats(s, 'stats'))
			if rts['channels'].has_key(s):
				channel_broadcast.update(rts['channels'][s])

			self.ws_broadcast_channel(s, channel_broadcast)

	
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
						#vote_type = "positive"
						self.db.execute("INSERT INTO session_votes (`session`, positive) VALUES (%s, 1) ON DUPLICATE KEY UPDATE positive=positive+1", t)
					elif re.search('\-1', s.text):
						#vote_type = "negative"
						self.db.execute("INSERT INTO session_votes (`session`, negative) VALUES (%s, 1) ON DUPLICATE KEY UPDATE negative=negative+1", t)
		

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
		
		broadcast.update(self.tweet_stats())
		
		broadcast['sessions'] = []
		
		for session in campboard['sessions']:
			stats = self.session_stats(session, 'stats')
			broadcast['sessions'].append([session, stats['votes'].get('cumulative', 0), stats.get('total_tweets', 0), stats.get('uniques', 0)])

		
		# Sorts the sessions list according to votes
		# http://wiki.python.org/moin/HowTo/Sorting/#KeyFunctions
		broadcast['sessions'] = sorted(broadcast['sessions'], key=lambda session: session[1], reverse=True)

		
		broadcast['sessions_number'] = len(campboard['sessions'])
		return broadcast


	@classmethod
	def tweet_stats(self, channel=None):
		'''Retrieves stats on tweets either for a channel, or across entire event'''
		stats = {}
		# Query our db for the relevant info
		if channel is not None:
			res = self.db.query('''SELECT COUNT(*) AS total_tweets, COUNT(DISTINCT user_id) as uniques FROM tweets WHERE id IN (
								SELECT tweet_id FROM hashtags_tweets WHERE hash_id IN
									(SELECT id FROM hashtags WHERE tag=%s)
								) ORDER BY created_at DESC''', channel)[0]
		else:
			res = self.db.query("SELECT COUNT(user_id) as total_tweets, COUNT(DISTINCT user_id) AS uniques FROM tweets")[0]
									
		stats['total_tweets'] = res.total_tweets		
		stats['uniques'] = res.uniques
		
		return stats


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
		
		res = self.db.query("SELECT positive, negative FROM session_votes WHERE session = %s", session)

		if res:
			votes['positive'] = res[0].positive or 0
			votes['negative'] = res[0].negative or 0
			votes['cumulative'] = votes['positive'] - votes['negative']
		else:
			votes['positive'] = votes['negative'] = votes['cumulative'] = 0

		return votes
		
	
	@classmethod
	def session_stats(self, session, selector='all'):
	
		session = session.strip()
		broadcast = {}
		
		broadcast['channel'] = session
	
		if selector in ['positive', 'negative', 'stats', 'all']:
			broadcast['votes'] = self.session_votes(session, selector)
		

		if selector in ['tweets', 'all']:					
			broadcast['recent_tweets'] = self.recent_tweets(session)
		

		if selector in ['tweetcount', 'stats', 'all']:
			broadcast.update(self.tweet_stats(session))

		return broadcast

	
	@classmethod
	def session_add(self, sess):
		campboard['sessions'].append(sess)
		print unicode(campboard['sessions'])
		self.db.execute('''INSERT INTO sessions (name) VALUES (%s) ON DUPLICATE KEY UPDATE name=%s''' , sess, sess)
		self.ws_broadcast_channel('main', self.general_update())

	
	@classmethod
	def session_remove(self, sess):
		campboard['sessions'].remove(sess)
		print unicode(campboard['sessions'])
		gen = self.general_update()
		gen['sessions'] = []
		gen['sessions'].append([sess, "DEL"]) # Set DEL to indicate removal
		gen['sessions_number'] = len(campboard['sessions'])		
		self.db.execute('''DELETE FROM sessions WHERE name=%s''' , sess)		
		self.ws_broadcast_channel('main', gen)
		
	
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
				i.write_message(data)
		except:
			pass # Fail silently


# Global application
campboard['application'] = Application()

if __name__ == "__main__":
	
	threading.Thread(target=Updater.start_updating, name="update_thread", args=('partyblankone', 'partyon', ['108958644'], [campboard['event_tag']])).start()
	print "Starting server"
	http_server = tornado.httpserver.HTTPServer(campboard['application'])
	http_server.listen(options.port)
	tornado.ioloop.IOLoop.instance().start()
	