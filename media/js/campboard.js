var CampBoard = CampBoard || {}

CampBoard.ws_init = function(){
	this.ws = new WebSocket("ws://ubuntuvm:8888/echo/");
	this.ws.onmessage = function(msg) {
		console.log("Received");
		console.log(msg);
		//var e = document.getElementById("echo");
		//e.innerHTML = e.innerHTML + "\r\n" + msg.data;
		//var l = $('<li></li>');
		//$(l).html(msg.data)
		//$(l).insertBefore($("#echo > li:first-child"))
		
		CampBoard.parse_message(msg);
	}
}

CampBoard.parse_message = function(msg) {
	console.log("Parsing!")
	console.log(msg.data)
	var data = JSON.parse(msg.data); // Extract the data
	
	if(data['total_tweets']) {
		$('#total-tweets').html(data['total_tweets']);
	}
	
	if(data['unique_tweeters']) {
		$('#unique-tweeters').html(data['unique-tweeters'])
	}
	
	if(data['recent_tweets']) {
		rts = data['recent_tweets']
		for(var i=0; i<rts.length; ++i) {
			var html = "<li><div class='tweet'>"
			html += "<a class='tweet-image' href='http://twitter.com/" + rts[i]['user']['screen_name'] + "'><img src='" + rts[i]['user']['profile_image_url'] + "'></a>";
			html +=	"<p class='tweet-text'>" + rts[i]['text'] + "</p>";
			html += "<small class='tweet-permalink' target='_blank'><a href='http://twitter.com/" + rts[i]['user']['screen_name'] + "/status/" + rts[i]['id'] + "/'>permalink</a>"; 
			html += "</div>";
			
			if($('#recent-tweets > .placeholder:first-child').length == 1) {
				$(html).insertBefore($('#recent-tweets > .placeholder:first-child'));
				$('#recent-tweets > .placeholder').remove();
			}
			else {
				$(html).insertBefore($('#recent-tweets > li:first-child'))
			}			
		}
	}
	
	if(data['sessions']) {
		var sess = data['sessions'];
		if(sess instanceof Object) {
			for(var i in sess) {
				var sess_format = "<span class='session-title'>" + i + "</span> - <span class='session-count'>" + sess[i] + "</span>";
				if($('#session-' + i).length == 0) { // Listing for session does not exist yet
					var html = "<li class='session' id='session-" + i + "'>"; // So we have to create our own <li>
					html += sess_format;
					html += "</li>";
					
					if($('#session-stats-list > .placeholder:first-child').length == 1) { // .. and place it in front of the placeholder if necessary
						$(html).insertBefore($('#session-stats-list > .placeholder:first-child'));
						$('#session-stats-list > .placeholder').remove();
					}
					else {
						$(html).insertBefore($('#session-stats-list > li:first-child'));
					}
				}
				else {
					$('#session-' + i).eq(0).html(sess_format); // Otherwise we just substitute the contents of the appropriate <li>
				}
			}
		}
	}	

}

if(jQuery) {
	$(window).load(function() {
		CampBoard.ws_init();
	})
	
	$(window).unload(function(){
		CampBoard.ws.send("Close");
		CampBoard.ws.close();
	})
}
