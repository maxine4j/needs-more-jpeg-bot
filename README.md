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

    $ sudo apt-get install python3
    $ sudo pip3 install praw pyimgur pillow
    
##Run:

    $ python3 jpegbot.py <args>
    
####Arguments:

| Switch | Description |
| --- | --- |
| -q --quality | Specify the quality used when compressing images (1 to 100) |
