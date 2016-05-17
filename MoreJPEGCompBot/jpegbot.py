"""
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

Author: Reddit: /u/Arwic
		GitHub: https://github.com/Arwic
"""

import traceback
import praw
import time
import sqlite3
import threading
from oauth import app_ua, app_id, app_secret, app_uri, app_scopes, app_code, app_refresh


subreddit = 'Arwic'  # this can be a multireddit, i.e. sub1+sub2+sub3
white_listed_authors = []
black_listed_authors = []
triggers = ['needs more jpeg compression']
max_pull = 100
pull_period = 20
code = 'W5Cz_AqAJiD2kAr5yV0c77Bg91k'

debug_truncation_len = 20


def login():
    r = praw.Reddit(app_ua)
    r.set_oauth_app_info(app_id, app_secret, app_uri)
    r.refresh_access_information(app_refresh)
    return r


def load_db():
    sql = sqlite3.connect('jpegbot.db')
    print('Loaded SQL Database')
    cur = sql.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS processed(ID TEXT)')
    print('Loaded Completed table')
    sql.commit()
    return sql, cur


def has_replied(sql, cur, cid):
    cur.execute('SELECT * FROM processed WHERE ID=?', [cid])
    if cur.fetchone():
        return True
    cur.execute('INSERT INTO processed VALUES(?)', [cid])
    sql.commit()
    return False


def _reply(comment):
    print('Replying to', comment.id, 'by', comment.author.name)
    while True:
        try:
            comment.reply('This is a test response')
            break
        except praw.errors.RateLimitExceeded as error:
            print('Rate limit exceeded! Sleeping for', error.sleep_time, 'seconds')
            time.sleep(error.sleep_time)


def reply(comment):
    t = threading.Thread(target=_reply, args=[comment])
    t.start()


def scan(reddit, sql, cur):
    print('Scanning', subreddit, '...')
    sr = reddit.get_subreddit(subreddit)
    submissions = sr.get_new(limit=max_pull)
    for submission in submissions:
        print('Parsing submission', submission.id, submission.name, 'by', submission.author)
        for c in submission.comments:
            # check if the author still exists
            try:
                c_author = c.author.name.lower()
                print('Parsing comment id="' + c.id + '" body="' + c.body[:debug_truncation_len] +
                      '..." author="' + c_author + '"')
            except AttributeError:
                print('Comment id="' + c.id + '" has been deleted or removed, ignoring it')
                continue

            # check if we have already replied to this comment
            if has_replied(sql, cur, c.id):
                print('Comment id="' + c.id + '" has been parsed, ignoring it')
                continue

            # check if the comment author is white listed
            if white_listed_authors != []:
                white_listed = False
                for author in white_listed_authors:
                    if author.lower() == c_author.lower():
                        white_listed = True
                        break
                if not white_listed:
                    print('User:', c_author, 'is not white listed, ignoring comment')
                    continue

            # check if the comment author is black listed
            if black_listed_authors != []:
                black_listed = False
                for author in black_listed_authors:
                    if author.lower() == c_author.lower():
                        black_listed = True
                        break
                if black_listed:
                    print('User:', c_author, 'is black listed, ignoring comment')
                    continue

            c_body = c.body.lower()
            if any(trigger in c_body.lower() for trigger in triggers):
                reply(c)


def main():
    reddit = login()
    sql, cur = load_db()
    while True:
        try:
            scan(reddit, sql, cur)
        except Exception:
            traceback.print_exc()
        print('Running again in', pull_period, 'seconds')
        sql.commit()
        time.sleep(pull_period)

if __name__ == '__main__':
    main()
