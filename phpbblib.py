#!/usr/bin/python3
import requests, sys, time, re
from bs4 import BeautifulSoup as Soup

class Forum:
    
    def __init__(self, url, name=None):
        self.url = url #TODO normalize url
        self.name = self.url if name is None else name
        self.session = requests.Session()
        self.logged_in = False
        self.last_request = 0
        self.last_post = 0
        self.request_limit = 1 #wait this many seconds between requests
        self.post_limit = 10 #wait this many seconds between posts
    
    def http_get(self, path, allow_errors=False, *args, **kwargs):
        curtime = time.perf_counter()
        if curtime - self.last_request < self.request_limit: # Wait 1 second between requests to avoid spamming
            time.sleep(self.request_limit - curtime  + self.last_request)
        response = self.session.get(self.url + path, *args, **kwargs)
        self.last_request = time.perf_counter()
        if not response.ok and not allow_errors:
            raise ConnectionError('HTTP {0} error ({1}) occured trying to fetch URL: {2}'.format(response.status_code, response.reason, response.url))
        return response
    
    def http_post(self, path, allow_errors=False, *args, **kwargs):
        curtime = time.perf_counter()
        if curtime - self.last_request < self.request_limit: # Wait 1 second between requests to avoid spamming
            time.sleep(self.request_limit - curtime  + self.last_request)
        response = self.session.post(self.url + path, *args, **kwargs)
        self.last_request = time.perf_counter()
        if not response.ok and not allow_errors:
            raise ConnectionError('HTTP {0} error ({1}) occured trying to fetch URL: {2}'.format(response.status_code, response.reason, response.url))
        return response
        
    def login(self, username, password):
        loginpage = self.http_get('/ucp.php?mode=login')
        loginrequest = self.http_post('/ucp.php?mode=login', data={'login': 'Login', 'username': username, 'password': password, 'sid': self.session.cookies['phpbb3_tf93i_sid']})
        if 'success' not in loginrequest.text: # Check for success. Can be made more robust later by parsing html
            raise AuthError('Failed to login')
        self.logged_in = True
        
    def logout(self):
        if not self.logged_in:
            raise AuthError("You can't logout if you're not logged in!")
        self.http_get('/ucp.php?mode=logout', params={'sid':self.session.cookies['phpbb3_tf93i_sid']})
        
    def get_thread(self, thread_id):
        return Thread(self, thread_id)
        
class Thread:
    
    def __init__(self, forum, thread_id):
        #TODO handle http 404
        self.forum = forum
        self.thread_id = thread_id
        self.reload()
            
    def reload(self):
        page = self.forum.http_get('/viewtopic.php', params={'t': self.thread_id})
        page_html = Soup(page.text, 'html.parser')
        first_post = Post(self, page_html.find(class_='post'))
        pagination = page_html.find(class_='pagination')
        self.post_count = int(re.search('([0-9]+) posts', pagination.text).group(1))
        self.created_date = first_post.post_date
        self.title = first_post.subject
        self.author = first_post.author
        if pagination.findChild('span') is not None:
            self.page_size = len(page_html.find_all(class_='post'))
        else:
            self.page_size = self.post_count
        navlinks = page_html.find(class_='navlinks')
        self.forum_id = int(re.search('[&?]f=(.*?)(?:&|$)', navlinks.find(name='li').find_all(name='a')[-1]['href']).group(1))


    def get_posts(self, start=0, end=None):
        if end is None:
            end = self.post_count
        if start < 0:
            raise IndexError('start ({0}) must be positive'.format(start))
        if end > self.post_count:
            raise IndexError('end ({0}) must be less than or equal to post_count ({1})'.format(end, self.post_count))
        posts = []
        while end-start > 0:
            page = self.forum.http_get('/viewtopic.php', params={'t': self.thread_id, 'start': start})
            page_html = Soup(page.text, 'html.parser')
            posts += self.get_posts_from_html(page_html)
            start += self.page_size
        return posts

    def get_post(self, index=0):
        return self.get_posts(start=index, end=index+1)[0]
            
    def make_post(self, message, subject=None, *, disable_bbcode=False, disable_smilies=False, disable_magic_url=False, attach_sig=True):
        #TODO handle errors (e.g. posting if not logged in on some forums)
        postingpage = self.forum.http_get('/posting.php?mode=reply', params={'f': self.forum_id, 't': self.thread_id})
        html = Soup(postingpage.text, 'html.parser')
        postdata = {
            'message': message,
            'post': 'Submit',
            'lastclick': str(int(html.find(attrs={'name':'lastclick'})['value'])-5),
            'creation_time': html.find(attrs={'name':'creation_time'})['value'],
            'form_token': html.find(attrs={'name':'form_token'})['value'],
            'topic_cur_post_id': html.find(attrs={'name':'topic_cur_post_id'})['value'],
            'subject': html.find(id='subject')['value'] if subject is None else subject
        }
        if disable_bbcode:
            postdata['disable_bbcode'] = 'on'
        if disable_smilies:
            postdata['disable_smilies'] = 'on'
        if disable_magic_url:
            postdata['disable_magic_url'] = 'on'
        if attach_sig:
            postdata['attach_sig'] = 'on'
        curtime = time.perf_counter()
        if curtime - self.forum.last_post < self.forum.post_limit:
            time.sleep(self.forum.post_limit - (curtime - self.forum.last_post))
        postrequest = self.forum.http_post('/posting.php?mode=reply', params={'f': self.forum_id, 't': self.thread_id}, data=postdata)
        #TODO test for success/failure
        self.forum.last_post = time.perf_counter()
            
    def get_posts_from_html(self, html):
        posts = []
        for i, post_div in enumerate(html.find_all(class_='post')):
            posts.append(Post(self, post_div))
        return posts
        
        
class Post:
    
    def __init__(self, thread, post_div):
        self.thread = thread
        self.post_id = post_div.get('id')[1:]
        self.subject = post_div.find('h3').text
        self.content_html = post_div.find(class_='content')
        self.content_text = self.content_html.text
        self.author, self.post_date = re.match('by (.*?) » (.*) ', post_div.find(class_='author').text).groups()
        self.url = self.thread.forum.url + '/viewtopic.php?t={0}#{1}'.format(self.thread.thread_id, self.post_id)
        
class AuthError(Exception):
    pass