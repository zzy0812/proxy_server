# -*- coding: utf-8 -*-

from socket import *
import sys
import time
import os
import errno
import re
import threading
import pickle

# count the number of sockets, nornal http requests and condition_GET requests
count_global = 0
count_http = 0
count_conditional = 0

# ========================================================================
# valid_host.txt records all the valid hosts with successful responds
# this is to solve the problem that sometimes the Referer does not have a complete server name
# thus, when that happens, the valid_host.txt will be checked to match for those requests
if not os.path.isfile('valid_host.txt'):
   with open('valid_host.txt', 'w') as f:
      f.write('')
# ========================================================================



# ========================================================================
# this function
# 1. takes in hostname and objectname, send the HTTP request
# 2. send the response to client and cache it
# 3. if the response contains Last-modified, add it to the pickle file
def http_request(hostname, objectname, tcpCliSock, message):

   c = socket(AF_INET, SOCK_STREAM)
   if hostname[-1] == '/':
      hostname = hostname[0:-1]
   addr = (hostname, 80)
   print "addr: ", addr
   # Connect to the socket to port 80
   # Fill in start.
   try:
      c.connect(addr)
   except error:
      print 'error when connecting to host'
      return False
   global count_http
   print "http_request %d connected!"%count_http

   print "connected to %s" %hostname
   # Fill in end.
   print 'objectname: ', objectname
   # print 'message: ', message

   # convert the localhost name and referer in the message those the one related to actual server
   pattern_Host = re.compile(r"(?<=Host:).+?(?=[;\s+])")
   message_h = pattern_Host.sub(' ' + hostname, message)
   # print 'message_h: ', message_h
   pattern_Referer = re.compile(r"(?<=Referer: http://).+?(?=[;\s+])")
   request_message = pattern_Referer.sub(hostname, message_h)

   # avoid duplication. e.g. 'GET www.ee.columbia.edu/ HTTP...' should be 'GET / HTTP...' because 'www.ee.columbia.edu' is already specified in the Host field
   if hostname in request_message.split()[1]:
      request_message = request_message.replace(hostname, '', 1)
   # avoid request like "GET // HTTP..." happen
   if "//" in request_message.split()[1]:
      request_message = request_message.replace('//', '/', 1)

   print "request_message is: ", request_message
   # Create a temporary file on this socket and ask port 80 for the file requested by the client
   fileobj_w = c.makefile('wb', 0) #Instead of using send and recv, we can use makefile

   try:

      fileobj_w.write(request_message)
      # Read the response into buffer
      # Fill in start.
      fileobj_r = c.makefile('rb', 0)
      response = fileobj_r.read()
      fileobj_w.close()
      fileobj_r.close()
      c.close()
      print "http request %d closed"%count_http
      lock.acquire()
      count_http += 1
      lock.release()
      if ('404 Not Found' in response) | ('400 Bad Request' in response) | ('301 Moved Permanently' in response):
         print 'wrong host'

         return False

      # Create a new file in the cache for the requested file.
      # Also send the response in the buffer to client socket and the corresponding file in the cache
      # # Fill in start
      # if objectname includes the hostname, remove it
      if hostname in objectname:
         objectname = objectname[objectname.index(hostname)+len(hostname):]
      if objectname[0] == '/':
         filename_before = hostname+objectname
      else:
         filename_before = hostname+'/'+objectname
      # make sure that the last character is not '/', this make sure that
      # users who type in 'www.ee.columbia.edu' and 'www.ee.columbia.edu/'
      # can get the same file
      if filename_before[-1] == '/':
         filename_before = filename_before[0:-1]
      # for situation like "www.ee.columbia.edu" + '/' + '/'
      if filename_before[-1] == '/':
         filename_before = filename_before[0:-1]

      print "hostname_before:", hostname
      print "objectname_before:", objectname
      print "filename_before: ",filename_before

      # replace / with . so that the filename can be valid
      filename_final = filename_before.replace('/','.')

      print "filename_final: ", filename_final
      with open(filename_final,"wb") as tmpFile:
         print "writing the response into the file %s" %filename_final
         tmpFile.write(response)
         print "writing finished!"
      print "have it cached"

      tcpCliSock.send(response)

      print "Sent the response"
      # print "the response is ", response
      print ("type(response): " + str(type(response)))
      print ("len(response): " +  str(len(response)))

      # if the response contains Last-Modified field, add it to the dictionary

      if 'Last-Modified' in response:
         # by observation, 'www.ee.columbia.edu' sends Last-Modified filed
         # but does not support conditional GET (always send back 200 back when it is supposed to be 304)
         # thus, skip the process to save loading time
         # check whether the object has the Last-Modified field in its tcp header
         if hostname != 'www.ee.columbia.edu':
            pattern_modified = re.compile("(?<=Last-Modified:).+(?=GMT)")
            last_modified = pattern_modified.findall(response)[0]+'GMT'
            # use pickle file to store the dictionary
            lock.acquire()
            if not os.path.isfile('obj_cached.pickle'):
               dic = {filename_final:last_modified}
               with open('obj_cached.pickle', 'wb') as handle:
                  pickle.dump(dic, handle)
                  print 'dumped %s to pickle file'%dic
            else:
               dic_new = {}
               with open('obj_cached.pickle', 'rb') as handle:
                  dic = pickle.load(handle)
                  dic[filename_final] = last_modified
                  dic_new = dic
               with open('obj_cached.pickle', 'wb') as handle:
                  pickle.dump(dic_new, handle)
                  print 'dumped %s to pickle file'%dic_new
            lock.release()
      # add the host to the valid_host.txt
      f = open('valid_host.txt','r')
      l = f.read().split()
      f.close()

      if hostname not in l:
         lock.acquire()
         f = open('valid_host.txt', 'a')
         f.write(hostname+'\n')
         f.close()
         lock.release()
         print hostname, 'added to the valid_host.txt!'
      return True

   except error as e:
      c.close()
      print "http request %d closed"%count_http
      lock.acquire()
      count_http += 1
      lock.release()

      if isinstance(e.args, tuple):
         print "errno is %d"%e[0]
         if e[0] == errno.EPIPE:
            # remote peer disconnected
            print "Detected remote disconnect"
         else:
            print 'error other than remote disconnect occurs: %s!'%e[0]
      return False
# ========================================================================



# ========================================================================
# this function perform the condition GET request, with given message, hostname, objectname
# last-modified time, etc. It will modify the message by adding If-Modified-Since filed in the header
def conditional_GET(hostname, objectname, tcpCliSock, message, last_modified):

   c = socket(AF_INET, SOCK_STREAM)
   if hostname[-1] == '/':
      hostname = hostname[0:-1]
   addr = (hostname, 80)
   print "addr: ", addr

   try:
      c.connect(addr)
   except error:
      print 'error when connecting to host'
      return False
   global count_conditional
   print "conditional_GET %d connected!" %count_conditional

   print "connected to %s" %hostname

   # convert the localhost name and referer in the message those the one related to actual server
   pattern_Host = re.compile(r"(?<=Host:).+?(?=[;\s+])")
   message_h = pattern_Host.sub(' ' + hostname, message)
   pattern_Referer = re.compile(r"(?<=Referer: http://).+?(?=[;\s+])")
   request_message = pattern_Referer.sub(hostname, message_h)

   # avoid duplication. e.g. 'GET www.ee.columbia.edu/ HTTP...' should be 'GET / HTTP...' because 'www.ee.columbia.edu' is already specified in the Host field
   if hostname in request_message.split()[1]:
      request_message = request_message.replace(hostname, '', 1)
   # avoid request like "GET // HTTP..." happen
   if "//" in request_message.split()[1]:
      request_message = request_message.replace('//', '/', 1)

   split_message = request_message.split("\r\n")
   new_split = []
   new_split.append(split_message[0])
   new_split.append(split_message[1])
   if_modified_since = "If-Modified-Since:%s"%last_modified
   new_split.append(if_modified_since)
   for i in range(2, len(split_message)):
      new_split.append(split_message[i])
   print new_split
   request_message =  '\r\n'.join(new_split)

   print "request_message is: ", request_message
   # Create a temporary file on this socket and ask port 80 for the file requested by the client
   fileobj_w = c.makefile('wb', 0) #Instead of using send and recv, we can use makefile

   try:

      fileobj_w.write(request_message)
      # Read the response into buffer
      # Fill in start.
      fileobj_r = c.makefile('rb', 0)
      response = fileobj_r.read()
      fileobj_w.close()
      fileobj_r.close()
      c.close()
      print " conditional_GET request %d losed"%count_conditional
      lock.acquire()
      count_conditional += 1
      lock.release()
      return response

   except error:
      c.close()
      print " conditional_GET request %d losed"%count_conditional
      lock.acquire()
      count_conditional += 1
      lock.release()
      print "conditional GET fails"
      return False
# ========================================================================



# ========================================================================
# this function checkes if an object exits, if it does, it will
# 1. check if the object has Last-Modified filed, if it does
# 2. call conditon_GET function to check if it is up-to-date
# 3. return the requested object or return False
# 4. update pickle file with the new Last-Modified if the cache is updated
def check_cache(hostname, objectname, tcpCliSock, message):
   try:
      # make sure that the hostname,objectname and filename have the right format
      if hostname[-1] == '/':
         hostname = hostname[0:-1]
      if hostname in objectname:
         objectname = objectname[objectname.index(hostname)+len(hostname):]
      if objectname[0] =='/':
         filename_before = hostname + objectname
      else:
         filename_before = hostname+'/'+objectname
      # make sure that the last character is not '/', this make sure that
      # users who type in 'www.ee.columbia.edu' and 'www.ee.columbia.edu/'
      # can get the same file
      if filename_before[-1] == '/':
         filename_before = filename_before[0:-1]
      if filename_before[-1] == '/':
         filename_before = filename_before[0:-1]

      # replace / with . so that the filename can be valid
      filename_final = filename_before.replace('/','.')

      # Check wether the file exist in the cache
      f = open(filename_final, "r")
      outputdata = f.readlines()
      print "found the file %s!"%filename_final
      f.close()

      # check whether the object has the Last-Modified field in its tcp header

      # record whether the response has been sent or not
      flag_tmp = 0

      # by observation, 'www.ee.columbia.edu' sends Last-Modified filed
      # but does not support conditional GET (always send back 200 back when it is supposed to be 304)
      # thus, skip the process to save loading time
      if hostname != 'www.ee.columbia.edu':

         lock.acquire()
         with open('obj_cached.pickle', 'rb') as handle:
            dic = pickle.load(handle)
         lock.release()

         if filename_final in dic and os.path.isfile('obj_cached.pickle'):

            last_modified = dic[filename_final]
            print 'the object has Last-Modified field: %s' %last_modified

            print 'sending the conditional GET...'
            response = conditional_GET(hostname, objectname, tcpCliSock, message, last_modified)

            # conditional_GET gets a response
            if response:
               # not modified, return the origianl cache
               if "304 Not Modified" in response:
                  print "The cache is up-to-date!"

               # 200 OK means that the file is outdated
               elif "200 OK" in response:
                  print "The cache is out dated."

                  # overwrite the old cache
                  lock.acquire()
                  with open(filename_final,"wb") as tmpFile:
                     print "writing the new object into the file %s" %filename_final
                     tmpFile.write(response)
                     print "writing finished!"
                     tcpCliSock.send(response)
                     print "response of lenght %d sent to client!"%len(response)
                     # indicate that response has been sent to the client
                     flag_tmp = 1
                  lock.release()

                  # update the pickle file with the latest Last-Modified value
                  pattern_modified = re.compile("(?<=Last-Modified:).+(?=GMT)")
                  last_modified_new = pattern_modified.findall(response)[0]+'GMT'
                  dic[filename_final] = last_modified_new
                  lock.acquire()
                  with open('obj_cached.pickle', 'wb') as handle:
                     pickle.dump(dic, handle)
                     print "dumped %s into pickle file"%dic
                  lock.release()

               else:
                  print "unexpected result from condition GET"

            else:
               print "The requested page does not support conditional GET"

      # the file is up-to-date, send the original cache
      if flag_tmp == 0:
         length_file = 0
         for i in outputdata:
            length_file += len(i)
            tcpCliSock.send(i)
         print "sent file of length %d to the client"%length_file

      return True

   except IOError:

      print "Did not find the object in the cache!"
      return False
# ========================================================================



# ========================================================================
# using multithread for socket connection
# the class inherits from threading
class ClientThread(threading.Thread):

   def __init__(self, ip, port, tcpCliSock):
      threading.Thread.__init__(self)
      self.ip = ip
      self.port = port
      self.tcpCliSock = tcpCliSock

   def run(self):

      global count_global
      print 'COUNT IS:  ', count_global
      print('Received a connection from:', self.ip, self.port)

      message = str(self.tcpCliSock.recv(1024).decode())# Fill in start. # Fill in end.
      print("message: " + message)
      print message.split()
      print type(message)
      print len(message.split())

      if not message:
         pass

      else:
            flag_unsolvable = 0
            # find the actual request url, after "localhost:8080"
            print 'message.split()[1]: ', message.split()[1]
            sub_request = message.split()[1].partition("/")[2]
            print 'message.split()[1].partition("/")[2]: ', sub_request
            # find the Referer, if any, from the message
            pattern_refer = re.compile(r"(?<=Referer:).+?(?=[;|\s+])")
            referer = pattern_refer.findall(message)

            # make sure that referer infomation is correctly used
            # ==============================================
            hostname = sub_request.partition("/")[0]

            objectname = sub_request[len(hostname):]
            # make sure request will work
            if objectname == '':
               objectname = '/'

            # if the Refer exists, parse it
            if referer:

               referer_value = referer[0].split("//")[-1].partition('/')[-1]
               print "referer_value: ", referer_value
               if referer_value[-1] == '/':
                  referer_value = referer_value[0:-1]

               # ideal result
               if (hostname == referer_value):
                  pass
                  # objectname = sub_request[len(hostname):]

               # if not, the host name is not included in the GET <sub request>
               else:
                  # get the valid host list
                  with open("valid_host.txt",'r') as f:
                     l = f.read().split()

                  # if the referer is a valid host
                  if referer_value in l:
                     # let the referer be the host, and the sub request be the object
                     hostname = referer_value
                     objectname = message.split()[1]

                  # this is for situation like
                  # GET www.robotics.stanford.edu/~ang/images/..
                  # Referer: www.robotics.standford.edu/~ang/global.css
                  elif hostname in l:
                     pass

                  else:
                     # mark if the valid host name hides in the Referer field
                     flag_local = 0
                     for i in l:
                        # if the hostname is partially hidden in the referer field
                        if i in referer_value:
                           hostname = i
                           flag_local = 1
                           objectname = message.split()[1]

                     # this is the situation when the referer and GET <sub request> both contain no host name
                     # it is rare but it happens in 'www.ee.columbia.edu'
                     # get the Cookie
                     if flag_local == 0:
                        flag_unsolvable = 1
            # ==============================================

            if flag_unsolvable == 0:
               print "hostname: ", hostname
               print "objectname: ", objectname

               # check if it exists, and perform other operations in the function
               result_check = check_cache(hostname, objectname, self.tcpCliSock, message)


               if result_check == False:

                  return_result = http_request(hostname, objectname, self.tcpCliSock, message)

                  if return_result == False:
                     print "tried all the method"
               else:
                  print "file exists and sent the response!"
            else:
               print "sorry, the object does not contain host server, unsolvable situation"
      self.tcpCliSock.close()
      print "socket ", count_global, " is closed"
      lock.acquire()
      count_global += 1
      lock.release()
# ========================================================================



tcpSerSock = socket(AF_INET, SOCK_STREAM)
Server_host = 'localhost'
Server_port = 8080
tcpSerSock.bind((Server_host, Server_port))
tcpSerSock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

# when performing file read/write, lock can avoid conflicts between threads
lock = threading.Lock()
threads = []

while True:
   tcpSerSock.listen(5)
   print('Ready to serve...')
   # start new thread for tcp connection
   (tcpCliSock, (host, ip)) = tcpSerSock.accept()
   newthread = ClientThread(host, ip, tcpCliSock)
   newthread.start()
   threads.append(newthread)

for t in threads:
    t.join()
