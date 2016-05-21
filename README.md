#Needs More JPEG Bot

This bot will reply to a user who comments about the poor quality of a submitted jpeg with a lower quality version of the same image.

##Author(s): 

/u/Arwic
  
##Features:
* Blacklist
* Whitelist
* Multiple trigger phrases

##Installation:

    $ git clone https://github.com/Arwic/NeedsMoreJPEGBot.git
    $ sudo apt-get install python3 libjpeg8 libjpeg62-dev libfreetype6 libfreetype6-dev
    $ sudo pip3 install praw pyimgur pillow
    
There is a bug in the version of PyImgur available from pip. To fix it, change line 34 of 

"/usr/local/lib/python3.4/dist-packages/pyimgur/\__init\__.py"

from

    from urlparse import urlparse

to

    from urllib.parse import urlparse
    
##Run:

    $ python3 jpegbot.py <args>
    
#####Arguments:

| Switch | Description |
| --- | --- |
| -q --quality | Specify the quality used when compressing images (1 to 100) |
