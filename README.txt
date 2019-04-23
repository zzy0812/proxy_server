
1. IP address: 'localhost'

2. port number: 8080

3. data structure for caching: 

   (1) data structure

       A dictionary. Each key is the file name of the cache object, and the value is the Last-Modified filed value for that cached object.

   (2) how to store it

       Use pickle file to store the dictionary

4. Bonus parts:

   (1) made the points better
      
       1) requests to the server
	
	     In order to get a better response from the server, the request sent from the proxy server to the server is inherited from the request message from the client, with some modifications on the first line and hearder fields. e.g. 'GET /www.cs.columbia.edu/ HTTP/1.1\r\nHost: localhost:8080\r\n' will become 'GET / HTTP/1.1\r\nHost: www.cs.columbia.edu\r\n'. 

	     The Host field is always modified. The first line will be modified if it contains valid server name. When sending the conditional GET, 'If-modified-Since' field will be added. Referer field will be modified to eliminate useless information for the request. The other header fields remain the same.

       2) URL tolerance

	     Since '/' is optional in some cases, e.g. 'www.cs.columbia.edu' is the same as 'www.cs.columbia.edu/', the program is modified to be able to handle both cases.

       3) Parsing information in the Header fields
	
	     Many requests from clients do not contain server name in the first line, and the server's host name might be hidden in the Referer field, thus, the program is modified to be able to get the most out of Referer field to send the correct request message. To achieve this, valid host log is also needed. (See the below)

       4) valid host log
	
	     Some request messages do not contain valid server name in the first line, and the Refer field only partially contains the server and other information, e.g. the Referer might be (after parsing) 'www.ee.columbia.edu/.../global.css', then how do we know what the correct server is? The solution I came up with is to store 'www.ee.columbia.edu' to a valid_host.txt file containing all the valid server names, and when the destination server can not be parsed from the request message in the normal way, the Refer field will be checked again the file to see if it contains any valid host. If it does, the valid host will be the server name.
 
	  5) modularization

	     Three functions are defined to perform different functions: http_request, conditional_GET and check_cache. Their main functionalities are:  http_request function sends the request to servers for objects that are not locally cached; check_cache function checks if the object is cached and calls condition_GET function to keep the cache up-to-date; condition_GET function performs the condition GET request and return its result to check_cache function.

   (2) multi-threading

	  To enable the proxy server to handle multiple requests at the same, threading module is imported. The ClientThread class inherits from threading.Thread class and its run() method is executed when socket is created. A lock object is created to prevent conflicts between threads when performing file read/write.
