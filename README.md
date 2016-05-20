#Reddit Bots

##Author(s): 

/u/Arwic

##Needs More JPEG Compression Bot: 
  
This bot will reply to a user who comments about the poor quality of a submitted jpeg with a lower quality version of the same image.
  
###Features:
* Blacklist
* Whitelist
* Multiple trigger phrases

##Installation:

    $ git clone https://github.com/Arwic/RedditBots.git
    $ sudo apt-get install python3 libjpeg8 libjpeg62-dev libfreetype6 libfreetype6-dev
    $ sudo pip3 install praw pyimgur pillow
    
##Run:

    $ python3 jpegbot.py <args>
    
#####Arguments:

| Switch | Description |
| --- | --- |
| -q --quality | Specify the quality used when compressing images (1 to 100) |
