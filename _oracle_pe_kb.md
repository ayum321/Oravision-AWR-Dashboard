# Oracle Performance Engineering Knowledge Base
## Source: Oracle Database Performance Tuning Guide (19c)

## 1. Oracle Performance Improvement Method (Official Steps)
Steps in the Oracle Performance Improvement Method
1.
Perform the following initial standard checks:
a.
Get candid feedback from users. Determine the performance project's scope
and subsequent performance goals, and performance goals for the future.
This process is key in future capacity planning.
b.
Get a full set of operating system, database, and application statistics from the
system when the performance is both good and bad. If these are not available,
then get whatever is available. Missing statistics are analogous to missing
evidence at a crime scene: They make detectives work harder and it is more
time-consuming.
c.
Sanity-check the operating systems of all computers involved with user
performance. By sanity-checking the operating system, you look for hardware
or operating system resources that are fully utilized. List any over-used
resources as symptoms for analysis later. In addition, check that all hardware
shows no errors or diagnostics.
2.
Check for the top ten most common mistakes with Oracle Database, and
determine if any of these are likely to be the problem. List these as symptoms for
later analysis. These are included because they represent the most likely
problems. ADDM automatically detects and reports nine of these top ten issues.
3.
Build a conceptual model of what is happening on the system using the symptoms
as clues to understand what caused the performance problems. See "A Sample
Decision Process for Performance Conceptual Modeling".
4.
Propose a series of remedy actions and the anticipated behavior to the system, then
apply them in the order that can benefit the application the most. ADDM produces
recommendations each with an expected benefit. A golden rule in performance work is
that you only change one thing at a time and then measure the differences. Unfortunately,
system downtime requirements might prohibit such a rigorous investigation method. If
multiple changes are applied at the same time, then try to ensure that they are isolated
so that the effects of each change can be independently validated.
5.
Validate that the changes made have had the desired effect, and see if the user's
perception of performance has improved. Otherwise, look for more bottlenecks, and
continue refining the conceptual model until your understanding of the application
becomes more accurate.
6.
Repeat the last three steps until performance goals are met or become impossible due to
other constraints.
This method identifies the biggest bottleneck and uses an objective approach to performance
improvement. The focus is on making large performance improvements by increasing
application efficiency and eliminating resource shortages and bottlenecks. In this process, it is
anticipated that minimal (less than 10%) performance gains are made from instance tuning,
and large gains (100% +) are made from isolating application inefficiencies.
A Sample Decision Process for Performance Conceptual Modeling
Conceptual modeling is almost deterministic. Howev

## 2. Top 10 Mistakes Found in Oracle Systems


## 3. Wait Event Root Cause Reference
Each wait event description from Oracle's official guide:

### buffer busy waits
buffer busy waits
This wait indicates that there are some buffers in the buffer cache that multiple processes are
attempting to access concurrently. Query V$WAITSTAT for the wait statistics for each class of
buffer. Common buffer classes that have buffer busy waits include data block, segment
header, undo header, and undo block.
Check the following V$SESSION_WAIT parameter columns:
•
P1: File ID
•
P2: Block ID
•
P3: Class ID
Causes
To determine the possible causes, first query V$SESSION to identify the value of
ROW_WAIT_OBJ# when the session waits for buffer busy waits. For example:
SELECT row_wait_obj# 
 FROM V$SESSION 
 WHERE EVENT = 'buffer busy waits';
To identify the object and object type contended for, query DBA_OBJECTS using the value for
ROW_WAIT_OBJ# that is returned from V$SESSION. For example:
SELECT owner, object_name, subobject_name, object_type
 FROM DBA_OBJECTS
 WHERE data_object_id = &row_wait_obj;
Actions
The action required depends on the class of block contended for and the actual segment.
Segment Header
If the contention is on the segment header, then this is most likely free list contention.
Automatic segment-space management in locally managed tablespaces eliminates the
need to specify the PCTUSED, FREELISTS, and FREELIST GROUPS parameters. If possible,
switch from manual space management to automatic segment-space management
(ASSM).
The following information is relevant if you are unable to use ASSM (for example,
because the tablespace uses dictionary space management).
A free list is a list of free data blocks that usually includes blocks existing in several
different extents within the segment. Free lists are composed of blocks in which free
space has not yet reached PCTFREE or used space has shrunk below PCTUSED.
Specify the number of process free lists with the FREELISTS parameter. The default
value of FREELISTS is one. The maximum value depends on the data block size.
To find the current setting for free lists for that segment, run the following:
SELECT SEGMENT_NAME, FREELISTS
 FROM DBA_SEGMENTS
 WHERE SEGMENT_NAME = segment name
 AND SEGMENT_TYPE = segment type;
Set free lists, or increase the number of free lists. If adding more free lists does not
alleviate the problem, then use free list groups (even in single instance this can make
a difference). If using Oracle RAC, then ensure that each instance has its own free list
group(s).
Oracle Database Concepts for information about automatic segment-space
management, free lists, 

### db file scattered read
db file scattered read
This event signifies that the user process is reading buffers into the SGA buffer cache and is
waiting for a physical I/O call to return. A db file scattered read issues a scattered read to
read the data into multiple discontinuous memory locations. A scattered read is usually a
multiblock read. It can occur for a fast full scan (of an index) in addition to a full table scan.
The db file scattered read wait event identifies that a full scan is occurring. When
performing a full scan into the buffer cache, the blocks read are read into memory locations
that are not physically adjacent to each other. Such reads are called scattered read calls,
because the blocks are scattered throughout memory. This is why the corresponding wait
event is called 'db file scattered read'. multiblock (up to DB_FILE_MULTIBLOCK_READ_COUNT
blocks) reads due to full scans into the buffer cache show up as waits for 'db file scattered
read'.
Check the following V$SESSION_WAIT parameter columns:
•
P1: The absolute file number
•
P2: The block being read
•
P3: The number of blocks (should be greater than 1)
Actions
On a healthy system, physical read waits should be the biggest waits after the idle waits.
However, also consider whether there are direct read waits (signifying full table scans with
parallel query) or db file scattered read waits on an operational (OLTP) system that should
be doing small indexed accesses.
Other things that could indicate excessive I/O load on the system include the following:
•
Poor buffer cache hit ratio
•
These wait events accruing most of the wait time for a user experiencing poor response
time
Managing Excessive I/O
There are several ways to handle excessive I/O waits. In the order of effectiveness, these are
as follows:
•
Reduce the I/O activity by SQL tuning.
•
Reduce the need to do I/O by managing the workload.
•
Gather system statistics with DBMS_STATS package, allowing the query optimizer to
accurately cost possible access paths that use full scans.
•
Use Automatic Storage Management.
•
Add more disks to reduce the number of I/Os for each disk.
•
Alleviate I/O hot spots by redistributing I/O across existing disks.
The first course of action should be to find opportunities to reduce I/O. Examine the SQL
statements being run by sessions waiting for these events and statements causing high
physical I/Os from V$SQLAREA. Factors that can adversely affect the execution plans
causing excessive I/O include the following:
•
Improperly 

### db file sequential read
db file sequential read
This event signifies that the user process is reading a buffer into the SGA buffer cache
and is waiting for a physical I/O call to return. A sequential read is a single-block read.
Single block I/Os are usually the result of using indexes. Rarely, full table scan calls
could get truncated to a single block call because of extent boundaries, or buffers
present in the buffer cache. These waits would also show up as db file sequential
read.
Check the following V$SESSION_WAIT parameter columns:
•
P1: The absolute file number
•
P2: The block being read
•
P3: The number of blocks (should be 1)
"db file scattered read" for information about managing excessive I/O,
inadequate I/O distribution, and finding the SQL causing the I/O and the
segment the I/O is performed on.
Actions
On a healthy system, physical read waits should be the biggest waits after the idle waits.
However, also consider whether there are db file sequential reads on a large data
warehouse that should be seeing mostly full table scans with parallel query.
The following figure shows differences between these wait events:
•
db file sequential read (single block read into one SGA buffer)
•
db file scattered read (multiblock read into many discontinuous SGA buffers)
•
direct read (single or multiblock read into the PGA, bypassing the SGA)
Figure 10-1 Scattered Read, Sequential Read, and Direct Path Read
DB File
Sequential Read
DB File
Scattered Read
Direct path 
read
Direct Path
Read
Database Buffer 
Cache
SGA Buffer Cache
Database Buffer 
Cache
SGA Buffer Cache
Sort Area
Hash Area
Process PGA
Bitmap Merge
Area
Session
Memory
Runtime
Area
Persistent
Area
direct path read and direct path read temp
When a session is reading buffers from disk directly into the PGA (opposed to the
buffer cache in SGA), it waits on this event. If the I/O subsystem does not support
asynchronous I/Os, then each wait corresponds to a physical read request.
If the I/O subsystem supports asynchronous I/O, then the process is able to overlap
issuing read requests with processing the blocks existing in the PGA. When the
process attempts to access a block in the PGA that has not yet been read from disk, it
then issues a wait call and updates the statistics for this event. Hence, the number of
waits is not necessarily the same as the number of read requests (unlike db file
scattered read and db file sequential read).
Check the following V$SESSION_WAIT parameter columns:
•
P1: File_id for the read call
•
P2: 

### direct path read
direct path read and direct path read temp
When a session is reading buffers from disk directly into the PGA (opposed to the
buffer cache in SGA), it waits on this event. If the I/O subsystem does not support
asynchronous I/Os, then each wait corresponds to a physical read request.
If the I/O subsystem supports asynchronous I/O, then the process is able to overlap
issuing read requests with processing the blocks existing in the PGA. When the
process attempts to access a block in the PGA that has not yet been read from disk, it
then issues a wait call and updates the statistics for this event. Hence, the number of
waits is not necessarily the same as the number of read requests (unlike db file
scattered read and db file sequential read).
Check the following V$SESSION_WAIT parameter columns:
•
P1: File_id for the read call
•
P2: Start block_id for the read call
•
P3: Number of blocks in the read call
Causes
This situation occurs in the following situations:
•
The sorts are too large to fit in memory and some of the sort data is written out
directly to disk. This data is later read back in, using direct reads.
•
Parallel execution servers are used for scanning data.
•
The server process is processing buffers faster than the I/O system can return the
buffers. This can indicate an overloaded I/O system.
Actions
The file_id shows if the reads are for an object in TEMP tablespace (sorts to disk) or
full table scans by parallel execution servers. This wait is the largest wait for large data
warehouse sites. However, if the workload is not a Decision Support Systems (DSS)
workload, then examine why this situation is happening.
Sorts to Disk
Examine the SQL statement currently being run by the session experiencing waits to
see what is causing the sorts. Query V$TEMPSEG_USAGE to find the SQL statement that
is generating the sort. Also query the statistics from V$SESSTAT for the session to
determine the size of the sort. See if it is possible to reduce the sorting by tuning the
SQL statement. If WORKAREA_SIZE_POLICY is MANUAL, then consider increasing the
SORT_AREA_SIZE for the system (if the sorts are not too big) or for individual processes.
If WORKAREA_SIZE_POLICY is AUTO, then investigate whether to increase
PGA_AGGREGATE_TARGET.
Full Table Scans
If tables are defined with a high degree of parallelism, then this setting could skew the
optimizer to use full table scans with parallel execution servers. Check the object being
read into using the direct path reads. If

### direct path write
direct path write and direct path write temp
When a process is writing buffers directly from PGA (as opposed to the DBWR writing them
from the buffer cache), the process waits on this event for the write call to complete.
Operations that could perform direct path writes include sorts on disk, parallel DML
operations, direct-path INSERTs, parallel create table as select, and some LOB operations.
Like direct path reads, the number of waits is not the same as number of write calls issued if
the I/O subsystem supports asynchronous writes. The session waits if it has processed all
buffers in the PGA and cannot continue work until an I/O request completes.
Oracle Database Administrator's Guide for information about direct-path inserts
Check the following V$SESSION_WAIT parameter columns:
•
P1: File_id for the write call
•
P2: Start block_id for the write call
•
P3: Number of blocks in the write call
Causes
This happens in the following situations:
•
Sorts are too large to fit in memory and are written to disk
•
Parallel DML are issued to create/populate objects
•
Direct path loads
Actions
For large sorts see "Sorts To Disk".
For parallel DML, check the I/O distribution across disks and ensure that the I/O
subsystem is adequately configured for the degree of parallelism.
enqueue (enq:) waits
Enqueues are locks that coordinate access to database resources. This event
indicates that the session is waiting for a lock that is held by another session.
The name of the enqueue is included as part of the wait event name, in the form enq:
enqueue_type - related_details. In some cases, the same enqueue type can be
held for different purposes, such as the following related TX types:
•
enq: TX - allocate ITL entry
•
enq: TX - contention
•
enq: TX - index contention
•
enq: TX - row lock contention
The V$EVENT_NAME view provides a complete list of all the enq: wait events.
You can check the following V$SESSION_WAIT parameter columns for additional
information:
•
P1: Lock TYPE (or name) and MODE
•
P2: Resource identifier ID1 for the lock
•
P3: Resource identifier ID2 for the lock
Oracle Database Reference for more information about Oracle Database
enqueues
Finding Locks and Lock Holders
Query V$LOCK to find the sessions holding the lock. For every session waiting for the
event enqueue, there is a row in V$LOCK with REQUEST <> 0. Use one of the following
two queries to find the sessions holding the locks and waiting for the locks.
If there are enqueue waits, you can see these us

### enqueue
enqueue
Look at V$ENQUEUE_STAT.
library cache latch
waits: library
cache, library
cache pin, and
library cache
lock
Latch contention
SQL parsing or
sharing
Check V$SQLAREA to see whether there are
SQL statements with a relatively high
number of parse calls or a high number of
child cursors (column VERSION_COUNT).
Check parse statistics in V$SYSSTAT and
their corresponding rate for each second.
log buffer space
Log buffer, I/O
Log buffer small
Slow I/O system
Check the statistic redo buffer
allocation retries in V$SYSSTAT. Check
configuring log buffer section in configuring
memory chapter. Check the disks that house
the online redo logs for resource contention.
log file sync
I/O, over- committing
Slow disks that store
the online logs
Un-batched commits
Check the disks that house the online redo
logs for resource contention. Check the
number of transactions (commits +
rollbacks) each second, from V$SYSSTAT.
•
"Wait Events Statistics" for detailed information on each event listed in
"Table 10-1" and for other information to cross-check
•
Oracle Database Reference for information about dynamic performance
views
•
My Oracle Support notices on buffer busy waits (34405.1) and free
buffer waits (62172.1). You can also access these notices and related
notices by searching for "busy buffer waits" and "free buffer waits" on My
Oracle Support website.
Additional Statistics
There are several statistics that can indicate performance problems that do not have
corresponding wait events.
Redo Log Space Requests Statistic
The V$SYSSTAT statistic redo log space requests indicates how many times a server
process had to wait for space in the online redo log, not for space in the redo log
buffer. Use this statistic and the wait events as an indication that you must tune
checkpoints, DBWR, or archiver activity, not LGWR. Increasing the size of the log
buffer does not help.
Read Consistency
Your system might spend excessive time rolling back changes to blocks in order to
maintain a consistent view. Consider the following scenarios:
•
If there are many small transactions and an active long-running query is running in
the background on the same table where the changes are happening, then the
query might need to roll back those changes often, in order to obtain a read-
consistent image of the table. Compare the following V$SYSSTAT statistics to
determine whether this is happening:
–
consistent: changes statistic indicates the number of times a database block
has rollback entries app

### free buffer waits
free buffer waits
This wait event indicates that a server process was unable to find a free buffer and has
posted the database writer to make free buffers by writing out dirty buffers. A dirty
buffer is a buffer whose contents have been modified. Dirty buffers are freed for reuse
when DBWR has written the blocks to disk.
Causes
DBWR may not be keeping up with writing dirty buffers in the following situations:
•
The I/O system is slow.
•
There are resources it is waiting for, such as latches.
•
The buffer cache is so small that DBWR spends most of its time cleaning out buffers for
server processes.
•
The buffer cache is so big that one DBWR process is not enough to free enough buffers
in the cache to satisfy requests.
Actions
If this event occurs frequently, then examine the session waits for DBWR to see whether
there is anything delaying DBWR.
If it is waiting for writes, then determine what is delaying the writes and fix it. Check the
following:
•
Examine V$FILESTAT to see where most of the writes are happening.
•
Examine the host operating system statistics for the I/O system. Are the write times
acceptable?
If I/O is slow:
•
Consider using faster I/O alternatives to speed up write times.
•
Spread the I/O activity across large number of spindles (disks) and controllers.
It is possible DBWR is very active because the cache is too small. Investigate whether this is
a probable cause by looking to see if the buffer cache hit ratio is low. Also use the
V$DB_CACHE_ADVICE view to determine whether a larger cache size would be advantageous.
If the cache size is adequate and the I/O is evenly spread, then you can potentially modify the
behavior of DBWR by using asynchronous I/O or by using multiple database writers.
Consider Multiple Database Writer (DBWR) Processes or I/O Slaves
Configuring multiple database writer processes, or using I/O slaves, is useful when the
transaction rates are high or when the buffer cache size is so large that a single DBWn
process cannot keep up with the load.
The DB_WRITER_PROCESSES initialization parameter lets you configure multiple database writer
processes (from DBW0 to DBW9 and from DBWa to DBWj). Configuring multiple DBWR
processes distributes the work required to identify buffers to be written, and it also distributes
the I/O load over these processes. Multiple db writer processes are highly recommended for
systems with multiple CPUs (at least one db writer for every 8 CPUs) or multiple processor
groups (at least as many db w

### latch events
latch events
A latch is a low-level internal lock used by Oracle Database to protect memory structures.
The latch free event is updated when a server process attempts to get a latch, and the latch
is unavailable on the first attempt.
There is a dedicated latch-related wait event for the more popular latches that often generate
significant contention. For those events, the name of the latch appears in the name of the
wait event, such as latch: library cache or latch: cache buffers chains. This enables
you to quickly figure out if a particular type of latch is responsible for most of the latch-related
contention. Waits for all other latches are grouped in the generic latch free wait event.
Oracle Database Concepts for more information on latches and internal locks
Actions
This event should only be a concern if latch waits are a significant portion of the wait time on
the system as a whole, or for individual users experiencing problems.
•
Examine the resource usage for related resources. For example, if the library
cache latch is heavily contended for, then examine the hard and soft parse rates.
•
Examine the SQL statements for the sessions experiencing latch contention to see
if there is any commonality.
Check the following V$SESSION_WAIT parameter columns:
•
P1: Address of the latch
•
P2: Latch number
•
P3: Number of times process has slept, waiting for the latch
Example: Find Latches Currently Waited For
SELECT EVENT, SUM(P3) SLEEPS, SUM(SECONDS_IN_WAIT) SECONDS_IN_WAIT
 FROM V$SESSION_WAIT
 WHERE EVENT LIKE 'latch%'
 GROUP BY EVENT;
A problem with the previous query is that it tells more about session tuning or instant
instance tuning than instance or long-duration instance tuning.
The following query provides more information about long duration instance tuning,
showing whether the latch waits are significant in the overall database time.
SELECT EVENT, TIME_WAITED_MICRO, 
 ROUND(TIME_WAITED_MICRO*100/S.DBTIME,1) PCT_DB_TIME 
 FROM V$SYSTEM_EVENT, 
 (SELECT VALUE DBTIME FROM V$SYS_TIME_MODEL WHERE STAT_NAME = 'DB time') S
 WHERE EVENT LIKE 'latch%'
 ORDER BY PCT_DB_TIME ASC;
A more general query that is not specific to latch waits is the following:
SELECT EVENT, WAIT_CLASS, 
 TIME_WAITED_MICRO,ROUND(TIME_WAITED_MICRO*100/S.DBTIME,1) PCT_DB_TIME
 FROM V$SYSTEM_EVENT E, V$EVENT_NAME N,
 (SELECT VALUE DBTIME FROM V$SYS_TIME_MODEL WHERE STAT_NAME = 'DB time') S
 WHERE E.EVENT_ID = N.EVENT_ID
 AND N.WAIT_CLASS NOT IN ('Idle', 'System I/O')
 ORDER BY PCT_DB_TIM

### log file parallel write
log file parallel write
This event involves writing redo records to the redo log files from the log buffer.
library cache pin
This event manages library cache concurrency. Pinning an object causes the heaps to
be loaded into memory. If a client wants to modify or examine the object, the client
must acquire a pin after the lock.
library cache lock
This event controls the concurrency between clients of the library cache. It acquires a
lock on the object handle so that either:
•
One client can prevent other clients from accessing the same object
•
The client can maintain a dependency for a long time which does not allow
another client to change the object
This lock is also obtained to locate an object in the library cache.
log buffer space
This event occurs when server processes are waiting for free space in the log buffer,
because all the redo is generated faster than LGWR can write it out.
Actions
Modify the redo log buffer size. If the size of the log buffer is reasonable, then ensure
that the disks on which the online redo logs reside do not suffer from I/O contention.
The log buffer space wait event could be indicative of either disk I/O contention on
the disks where the redo logs reside, or of a too-small log buffer. Check the I/O profile
of the disks containing the redo logs to investigate whether the I/O system is the
bottleneck. If the I/O system is not a problem, then the redo log buffer could be too
small. Increase the size of the redo log buffer until this event is no longer significant.
log file switch
There are two wait events commonly encountered:
•
log file switch (archiving needed)
•
log file switch (checkpoint incomplete)
In both of the events, the LGWR cannot switch into the next online redo log file. All the
commit requests wait for this event.
Actions
For the log file switch (archiving needed) event, examine why the archiver cannot archive
the logs in a timely fashion. It could be due to the following:
•
Archive destination is running out of free space.
•
Archiver is not able to read redo logs fast enough (contention with the LGWR).
•
Archiver is not able to write fast enough (contention on the archive destination, or not
enough ARCH processes). If you have ruled out other possibilities (such as slow disks or
a full archive destination) consider increasing the number of ARCn processes. The
default is 2.
•
If you have mandatory remote shipped archive logs, check whether this process is
slowing down because of network delays or the write is

### library cache pin
library cache pin
This event manages library cache concurrency. Pinning an object causes the heaps to
be loaded into memory. If a client wants to modify or examine the object, the client
must acquire a pin after the lock.
library cache lock
This event controls the concurrency between clients of the library cache. It acquires a
lock on the object handle so that either:
•
One client can prevent other clients from accessing the same object
•
The client can maintain a dependency for a long time which does not allow
another client to change the object
This lock is also obtained to locate an object in the library cache.
log buffer space
This event occurs when server processes are waiting for free space in the log buffer,
because all the redo is generated faster than LGWR can write it out.
Actions
Modify the redo log buffer size. If the size of the log buffer is reasonable, then ensure
that the disks on which the online redo logs reside do not suffer from I/O contention.
The log buffer space wait event could be indicative of either disk I/O contention on
the disks where the redo logs reside, or of a too-small log buffer. Check the I/O profile
of the disks containing the redo logs to investigate whether the I/O system is the
bottleneck. If the I/O system is not a problem, then the redo log buffer could be too
small. Increase the size of the redo log buffer until this event is no longer significant.
log file switch
There are two wait events commonly encountered:
•
log file switch (archiving needed)
•
log file switch (checkpoint incomplete)
In both of the events, the LGWR cannot switch into the next online redo log file. All the
commit requests wait for this event.
Actions
For the log file switch (archiving needed) event, examine why the archiver cannot archive
the logs in a timely fashion. It could be due to the following:
•
Archive destination is running out of free space.
•
Archiver is not able to read redo logs fast enough (contention with the LGWR).
•
Archiver is not able to write fast enough (contention on the archive destination, or not
enough ARCH processes). If you have ruled out other possibilities (such as slow disks or
a full archive destination) consider increasing the number of ARCn processes. The
default is 2.
•
If you have mandatory remote shipped archive logs, check whether this process is
slowing down because of network delays or the write is not completing because of errors.
Depending on the nature of bottleneck, you might need to redistribute I/O

### library cache lock
library cache lock
This event controls the concurrency between clients of the library cache. It acquires a
lock on the object handle so that either:
•
One client can prevent other clients from accessing the same object
•
The client can maintain a dependency for a long time which does not allow
another client to change the object
This lock is also obtained to locate an object in the library cache.
log buffer space
This event occurs when server processes are waiting for free space in the log buffer,
because all the redo is generated faster than LGWR can write it out.
Actions
Modify the redo log buffer size. If the size of the log buffer is reasonable, then ensure
that the disks on which the online redo logs reside do not suffer from I/O contention.
The log buffer space wait event could be indicative of either disk I/O contention on
the disks where the redo logs reside, or of a too-small log buffer. Check the I/O profile
of the disks containing the redo logs to investigate whether the I/O system is the
bottleneck. If the I/O system is not a problem, then the redo log buffer could be too
small. Increase the size of the redo log buffer until this event is no longer significant.
log file switch
There are two wait events commonly encountered:
•
log file switch (archiving needed)
•
log file switch (checkpoint incomplete)
In both of the events, the LGWR cannot switch into the next online redo log file. All the
commit requests wait for this event.
Actions
For the log file switch (archiving needed) event, examine why the archiver cannot archive
the logs in a timely fashion. It could be due to the following:
•
Archive destination is running out of free space.
•
Archiver is not able to read redo logs fast enough (contention with the LGWR).
•
Archiver is not able to write fast enough (contention on the archive destination, or not
enough ARCH processes). If you have ruled out other possibilities (such as slow disks or
a full archive destination) consider increasing the number of ARCn processes. The
default is 2.
•
If you have mandatory remote shipped archive logs, check whether this process is
slowing down because of network delays or the write is not completing because of errors.
Depending on the nature of bottleneck, you might need to redistribute I/O or add more space
to the archive destination to alleviate the problem. For the log file switch (checkpoint
incomplete) event:
•
Check if DBWR is slow, possibly due to an overloaded or slow I/O system. Check the
DBWR write

### log buffer space
log buffer space
Log buffer, I/O
Log buffer small
Slow I/O system
Check the statistic redo buffer
allocation retries in V$SYSSTAT. Check
configuring log buffer section in configuring
memory chapter. Check the disks that house
the online redo logs for resource contention.
log file sync
I/O, over- committing
Slow disks that store
the online logs
Un-batched commits
Check the disks that house the online redo
logs for resource contention. Check the
number of transactions (commits +
rollbacks) each second, from V$SYSSTAT.
•
"Wait Events Statistics" for detailed information on each event listed in
"Table 10-1" and for other information to cross-check
•
Oracle Database Reference for information about dynamic performance
views
•
My Oracle Support notices on buffer busy waits (34405.1) and free
buffer waits (62172.1). You can also access these notices and related
notices by searching for "busy buffer waits" and "free buffer waits" on My
Oracle Support website.
Additional Statistics
There are several statistics that can indicate performance problems that do not have
corresponding wait events.
Redo Log Space Requests Statistic
The V$SYSSTAT statistic redo log space requests indicates how many times a server
process had to wait for space in the online redo log, not for space in the redo log
buffer. Use this statistic and the wait events as an indication that you must tune
checkpoints, DBWR, or archiver activity, not LGWR. Increasing the size of the log
buffer does not help.
Read Consistency
Your system might spend excessive time rolling back changes to blocks in order to
maintain a consistent view. Consider the following scenarios:
•
If there are many small transactions and an active long-running query is running in
the background on the same table where the changes are happening, then the
query might need to roll back those changes often, in order to obtain a read-
consistent image of the table. Compare the following V$SYSSTAT statistics to
determine whether this is happening:
–
consistent: changes statistic indicates the number of times a database block
has rollback entries applied to perform a consistent read on the block.
Workloads that produce a great deal of consistent changes can consume a
great deal of resources.
–
consistent gets: statistic counts the number of logical reads in consistent
mode.
•
If there are few very, large rollback segments, then your system could be spending
a lot of time rolling back the transaction table during delayed block cleanout in
o

### log file switch
log file switch
There are two wait events commonly encountered:
•
log file switch (archiving needed)
•
log file switch (checkpoint incomplete)
In both of the events, the LGWR cannot switch into the next online redo log file. All the
commit requests wait for this event.
Actions
For the log file switch (archiving needed) event, examine why the archiver cannot archive
the logs in a timely fashion. It could be due to the following:
•
Archive destination is running out of free space.
•
Archiver is not able to read redo logs fast enough (contention with the LGWR).
•
Archiver is not able to write fast enough (contention on the archive destination, or not
enough ARCH processes). If you have ruled out other possibilities (such as slow disks or
a full archive destination) consider increasing the number of ARCn processes. The
default is 2.
•
If you have mandatory remote shipped archive logs, check whether this process is
slowing down because of network delays or the write is not completing because of errors.
Depending on the nature of bottleneck, you might need to redistribute I/O or add more space
to the archive destination to alleviate the problem. For the log file switch (checkpoint
incomplete) event:
•
Check if DBWR is slow, possibly due to an overloaded or slow I/O system. Check the
DBWR write times, check the I/O system, and distribute I/O if necessary.
•
Check if there are too few, or too small redo logs. If you have a few redo logs or small
redo logs (for example, 2 x 100k logs), and your system produces enough redo to cycle
through all of the logs before DBWR has been able to complete the checkpoint, then
increase the size or number of redo logs.
log file sync
When a user session commits (or rolls back), the session's redo information must be flushed
to the redo logfile by LGWR. The server process performing the COMMIT or ROLLBACK waits
under this event for the write to the redo log to complete.
Actions
If this event's waits constitute a significant wait on the system or a significant amount of time
waited by a user experiencing response time issues or on a system, then examine the
average time waited.
If the average time waited is low, but the number of waits are high, then the application might
be committing after every INSERT, rather than batching COMMITs. Applications can reduce the
wait by committing after 50 rows, rather than every row.
If the average time waited is high, then examine the session waits for the log writer and see
what it is spending mos

### log file sync
log file sync
I/O, over- committing
Slow disks that store
the online logs
Un-batched commits
Check the disks that house the online redo
logs for resource contention. Check the
number of transactions (commits +
rollbacks) each second, from V$SYSSTAT.
•
"Wait Events Statistics" for detailed information on each event listed in
"Table 10-1" and for other information to cross-check
•
Oracle Database Reference for information about dynamic performance
views
•
My Oracle Support notices on buffer busy waits (34405.1) and free
buffer waits (62172.1). You can also access these notices and related
notices by searching for "busy buffer waits" and "free buffer waits" on My
Oracle Support website.
Additional Statistics
There are several statistics that can indicate performance problems that do not have
corresponding wait events.
Redo Log Space Requests Statistic
The V$SYSSTAT statistic redo log space requests indicates how many times a server
process had to wait for space in the online redo log, not for space in the redo log
buffer. Use this statistic and the wait events as an indication that you must tune
checkpoints, DBWR, or archiver activity, not LGWR. Increasing the size of the log
buffer does not help.
Read Consistency
Your system might spend excessive time rolling back changes to blocks in order to
maintain a consistent view. Consider the following scenarios:
•
If there are many small transactions and an active long-running query is running in
the background on the same table where the changes are happening, then the
query might need to roll back those changes often, in order to obtain a read-
consistent image of the table. Compare the following V$SYSSTAT statistics to
determine whether this is happening:
–
consistent: changes statistic indicates the number of times a database block
has rollback entries applied to perform a consistent read on the block.
Workloads that produce a great deal of consistent changes can consume a
great deal of resources.
–
consistent gets: statistic counts the number of logical reads in consistent
mode.
•
If there are few very, large rollback segments, then your system could be spending
a lot of time rolling back the transaction table during delayed block cleanout in
order to find out exactly which system change number (SCN) a transaction was
committed. When Oracle Database commits a transaction, all modified blocks are
not necessarily updated with the commit SCN immediately. In this case, it is done
later on demand when the block is r

## 4. Buffer Cache Tuning Guide
V$DB_CACHE_ADVICE View
•
Calculating the Buffer Cache Hit Ratio
•
Interpreting the Buffer Cache Hit Ratio
•
Increasing Memory Allocated to the Database Buffer Cache
•
Reducing Memory Allocated to the Database Buffer Cache
Using the V$DB_CACHE_ADVICE View
The V$DB_CACHE_ADVICE view shows the simulated miss rates for a range of potential
buffer cache sizes. This view assists in cache sizing by providing information that
predicts the number of physical reads for each potential cache size. The data also
includes a physical read factor, which is a factor by which the current number of
physical reads is estimated to change if the buffer cache is resized to a given value.
However, physical reads do not necessarily indicate disk reads in Oracle Database,
because physical reads may be accomplished by reading from the file system cache.
Hence, the relationship between successfully finding a block in the cache and the size
of the cache is not always a smooth distribution. When sizing the buffer pool, avoid
using additional buffers that do not contribute (or contribute very little) to the cache hit
ratio.
The following figure illustrates the relationship between physical I/O ratio and buffer
cache size.
Figure 13-1 Physical I/O Ratio and Buffer Cache Size
Buffers
Phys I/O Ratio
~0.5
~0.1
Actual
Intuitive
A
B
C
Examining the example illustrated in the above figure leads to the following observations:
•
As the number of buffers increases, the physical I/O ratio decreases.
•
The decrease in the physical I/O between points A and B and points B and C is not
smooth, as indicated by the dotted line in the graph.
•
The benefit from increasing buffers from point A to point B is considerably higher than
from point B to point C.
•
The benefit from increasing buffers decreases as the number of buffers increases.
There is some overhead associated with using this advisory view. When the advisory is
enabled, there is a small increase in CPU usage, because additional bookkeeping is
required. To reduce both the CPU and memory overhead associated with bookkeeping,
Oracle Database uses sampling to gather cache advisory statistics. Sampling is not used if
the number of buffers in a buffer pool is small to begin with.
To use the V$DB_CACHE_ADVICE view:
1.
Set the value of the DB_CACHE_ADVICE initialization parameter to ON.
This enables the advisory view. The DB_CACHE_ADVICE parameter is dynamic, so the
advisory can be enabled and disabled dynamically to enable you to collect advisory data
for a specific workload.
2.
Run a representative workload on the database instance.
Allow the workload to stabilize before querying the V$DB_CACHE_ADVICE view.
3.
Query the V$DB_CACHE_ADVICE view.
The following example shows a query of this view that returns the predicted I/O requirement
for the default buffer pool for various cache sizes.
COLUMN size_for_estimate FORMAT 999,999,999,999 heading 'Cache Size (MB)'
COLUMN buffers_for_estimate FORMAT 999,999,999 heading 'Buffers'
COLUMN estd_physical_read_factor FORMAT 999.90 heading 'Estd Phys|Read Factor'
COLUMN estd_physical_reads FORMAT 999,999,999 heading 'Estd Phys| Reads'
SELECT size_for_estimate, buffers_for_estimate, estd_physical_read_factor,
 estd_physical_reads
FROM V$DB_CACHE_ADVICE
WHERE name = 'DEFAULT'
 AND block_size = (SELECT value FROM V$PARAMETER WHERE name = 'db_block_size')
 AND advice_status = 'ON';
The output of this query might look like the following:
 Estd Phys Estd Phys
 Cache Size (MB) Buffers Read Factor Reads
---------------- ------------ ----------- ------------
 30 3,802 18.70 192,317,943 10% of Current Size 
 60 7,604 12.83 131,949,536
 91 11,406 7.38 75,865,861
 121 15,208 4.97 51,111,658
 152 19,010 3.64 37,460,786
 182 22,812 2.50 25,668,196
 212 26,614 1.74 17,850,847
 243 30,416 1.33 13,720,149
 273 34,218 1.13 11,583,180
 304 38,020 1.00 10,282,475 Current Size 
 334 41,822 .93 9,515,878
 364 45,624 .87 8,909,026
 395 49,426 .83 8,495,039
 424 53,228 .79 8,116,496
 456 57,030 .76 7,824,764

## 5. Shared Pool / Library Cache Tuning
Library Cache Concepts
•
Data Dictionary Cache Concepts
•
SQL Sharing Criteria
Library Cache Concepts
The library cache stores executable forms of SQL cursors, PL/SQL programs, and
Java classes, which are collectively referred to as the application code. This section
focuses on tuning as it relates to the application code.
When the application code is executed, Oracle Database attempts to reuse existing
code if it has been executed previously and can be shared. If the parsed
representation of the SQL statement exists in the library cache and it can be shared,
then the database reuses the existing code. This is known as a soft parse, or a library
cache hit. If Oracle Database cannot use the existing code, then the database must
build a new executable version of the application code. This is known as a hard parse,
or a library cache miss. For information about when SQL and PL/SQL statements can
be shared, see "SQL Sharing Criteria".
In order to perform a hard parse, Oracle Database uses more resources than during a
soft parse. Resources used for a soft parse include CPU and library cache latch gets.
Resources required for a hard parse include additional CPU, library cache latch gets,
and shared pool latch gets. A hard parse may occur on either the parse step or the execute
step when processing a SQL statement.
When an application makes a parse call for a SQL statement, if the parsed representation of
the statement does not exist in the library cache, then Oracle Database parses the statement
and stores the parsed form in the shared pool. To reduce library cache misses on parse calls,
ensure that all sharable SQL statements are stored in the shared pool whenever possible.
When an application makes an execute call for a SQL statement, if the executable portion of
the SQL statement is aged out (or deallocated) from the library cache to make room for
another statement, then Oracle Database implicitly reparses the statement to create a new
shared SQL area for it, and executes the statement. This also results in a hard parse. To
reduce library cache misses on execution calls, allocate more memory to the library cache.
For more information about hard and soft parsing, see "SQL Execution Efficiency".
Data Dictionary Cache Concepts
Information stored in the data dictionary cache includes:
•
Usernames
•
Segment information
•
Profile data
•
Tablespace information
•
Sequence numbers
The data dictionary cache also stores descriptive information, or metadata, about schema
objects. Oracle Database uses this metadata when parsing SQL cursors or during the
compilation of PL/SQL programs.
SQL Sharing Criteria
Oracle Database automatically determines whether a SQL statement or PL/SQL block being
issued is identical to another statement currently in the shared pool.
To compare the text of the SQL statement to the existing SQL statements in the shared pool,
Oracle Database performs the following steps:
1.
The text of the SQL statement is hashed.
If there is no matching hash value, then the SQL statement does not currently exist in the
shared pool, and a hard parse is performed.
2.
If there is a matching hash value for an existing SQL statement in the shared pool, then
the text of the matched statement is compared to the text of the hashed statement to
verify if they are identical.
The text of the SQL statements or PL/SQL blocks must be identical, character for
character, including spaces, case, and comments. For example, the following statements
cannot use the same shared SQL area:
SELECT * FROM employees;
SELECT * FROM Employees;
SELECT * FROM employees;
Also, SQL statements that differ only in literals cannot use the same shared SQL area.
For example, the following statements do not resolve to the same SQL area:
SELECT count(1) FROM employees WHERE manager_id = 121;
SELECT count(1) FROM employees WHERE manager_id = 247;
The only exception to this rule is when the CURSOR_SHARING parameter is set to
FORCE, in which case similar statements can share 

## 6. PGA Tuning


## 7. Oracle Official Wait Event → Cause Table
Table of Wait Events and Potential Causes
Table 10-1 links wait events to possible causes and gives an overview of the Oracle data that
could be most useful to review next.
Table 10-1 Wait Events and Potential Causes
Wait Event
General Area
Possible Causes
Look for / Examine
buffer busy
waits
Buffer cache, DBWR
Depends on buffer
type. For example,
waits for an index
block may be caused
by a primary key that
is based on an
ascending sequence.
Examine V$SESSION while the problem is
occurring to determine the type of block in
contention.
free buffer
waits
Buffer cache, DBWR,
I/O
Slow DBWR (possibly
due to I/O?)
Cache too small
Examine write time using operating system
statistics. Check buffer cache statistics for
evidence of too small cache.
db file
scattered read
I/O, SQL statement
tuning
Poorly tuned SQL
Slow I/O system
Investigate V$SQLAREA to see whether there
are SQL statements performing many disk
reads. Cross-check I/O system and
V$FILESTAT for poor read time.
db file
sequential read
I/O, SQL statement
tuning
Poorly tuned SQL
Slow I/O system
Investigate V$SQLAREA to see whether there
are SQL statements performing many disk
reads. Cross-check I/O system and
V$FILESTAT for poor read time.
enqueue waits (waits
starting with enq:)
Locks
Depends on type of
enqueue
Look at V$ENQUEUE_STAT.
library cache latch
waits: library
cache, library
cache pin, and
library cache
lock
Latch contention
SQL parsing or
sharing
Check V$SQLAREA to see whether there are
SQL statements with a relatively high
number of parse calls or a high number of
child cursors (column VERSION_COUNT).
Check parse statistics in V$SYSSTAT and
their corresponding rate for each second.
log buffer space
Log buffer, I/O
Log buffer small
Slow I/O system
Check the statistic redo buffer
allocation retries in V$SYSSTAT. Check
configuring log buffer section in configuring
memory chapter. Check the disks that house
the online redo logs for resource contention.
log file sync
I/O, over- committing
Slow disks that store
the online logs
Un-batched commits
Check the disks that house the online redo
logs for resource contention. Check the
number of transactions (commits +
rollbacks) each second, from V$SYSSTAT.
•
"Wait Events Statistics" for detailed information on each event listed in
"Table 10-1" and for other information to cross-check
•
Oracle Database Reference for information about dynamic performance
views
•
My Oracle Support notices on buffer busy waits (34405.1) and free
buffer waits (62172.1). You can also access these notices and related
notices by searching for "busy buffer waits" and "free buffer waits" on My
Oracle Support website.
Additional Statistics
There are several statistics that can indicate performance problems that do not have
corresponding wait events.
Redo Log Space Requests Statistic
The V$SYSSTAT statistic redo log space requests indicates how many times a server
process had to wait for space in the online redo log, not for space in the redo log
buffer. Use this statistic and the wait events as an indication that you must tune
checkpoints, DBWR, or archiver activity, not LGWR. Increasing the size of the log
buffer does not help.
Read Consistency
Your system might spend excessive time rolling back changes to blocks in order to
maintain a consistent view. Consider the following scenarios:
•
If there are many small transactions and an active long-running query is running in
the background on the same table where the changes are happening, then the
query might need to roll back those changes often, in order to obtain a read-
consistent image of the table. Compare the following V$SYSSTAT statistics to
determine whether this is happening:
–
consistent: changes statistic indicates the number of times a database block
has rollback entries applied to perform a consistent read on the block.
Workloads that produce a great deal of consistent changes can consume a
great deal of resources.
–
consistent gets: statistic counts the number of logical reads in consistent
mode.
•
If there are few very, large rollback segments, then your system could be spending
a lot of time rolling back the transaction table during delayed block cleanout in
order to find out exactly which system change number (SCN) a transaction was
committed. When Oracle Database commits a transaction, all modified blocks are
not necessarily updated with the commit SCN immediately. In this case, it is done
later on demand when the block is read or updated. This is called delayed block
cleanout.
The ratio of the following V$SYSSTAT statistics should be close to one:
ratio = transaction tables consistent reads - undo records applied /
 transaction tables consistent read rollbacks
The recommended solution is to use automatic undo management.
•
If there are insufficient rollback segments, then there is rollback segment (header or
block) contention. Evidence of this problem is available by the following:
–
Comparing the number of WAITS to the number of GETS in V$ROLLSTAT; the proportion
of 

## 8. Drill-Down Methodology for Bottlenecks
Using Wait Event Statistics to Drill Down to Bottlenecks
Whenever an Oracle process waits for something, it records the wait using one of a set of
predefined wait events. These wait events are grouped in wait classes. The Idle wait class
groups all events that a process waits for when it does not have work to do and is waiting for
more work to perform. Non-idle events indicate nonproductive time spent waiting for a
resource or action to complete.
Note:
Not all symptoms can be evidenced by wait events. See "Additional Statistics" for
the statistics that can be checked.
The most effective way to use wait event data is to order the events by the wait time. This is
only possible if TIMED_STATISTICS is set to true. Otherwise, the wait events can only be
ranked by the number of times waited, which is often not the ordering that best represents the
problem.
To get an indication of where time is spent, follow these steps:
1.
Examine the data collection for V$SYSTEM_EVENT. The events of interest should be
ranked by wait time.
Identify the wait events that have the most significant percentage of wait time. To
determine the percentage of wait time, add the total wait time for all wait events,
excluding idle events, such as Null event , SQL*Net message from client,
SQL*Net message to client, and SQL*Net more data to client. Calculate the
relative percentage of the five most prominent events by dividing each event's wait
time by the total time waited for all events.
Alternatively, look at the Top 5 Timed Events section at the beginning of the
Automatic Workload Repository report. This section automatically orders the wait
events (omitting idle events), and calculates the relative percentage:
Top 5 Timed Events
~~~~~~~~~~~~~~~~~~ % Total
Event Waits Time (s) Call Time
-------------------------------------- ------------ ----------- ---------
CPU time 559 88.80
log file parallel write 2,181 28 4.42
SQL*Net more data from client 516,611 27 4.24
db file parallel write 13,383 13 2.04
db file sequential read 563 2 .27
In some situations, there might be a few events with similar percentages. This can
provide extra evidence if all the events are related to the same type of resource
request (for example, all I/O related events).
2.
Look at the number of waits for these events, and the average wait time. For
example, for I/O related events, the average time might help identify whether the
I/O system is slow. The following example of this data is taken from the Wait Event
section of the AWR report:
 Avg
 Total Wait wait Waits
Event Waits Timeouts Time (s) (ms) /txn
--------------------------- --------- --------- ---------- ------ ---------
log file parallel write 2,181 0 28 13 41.2
SQL*Net more data from clie 516,611 0 27 0 9,747.4
db file parallel write 13,383 0 13 1 252.5
3.
The top wait events identify the next places to investigate. A table of common wait
events is listed in Table 10-1. It is usually a good idea to also have quick look at
high-load SQL.
4.
Examine the related data indicated by the wait events to see what other
information this data provides. Determine whether this information is consistent
with the wait event data. In most situations, there is enough data to begin
developing a theory about the potential causes of the performance bottleneck.
5.
To determine whether this theory is valid, cross-check data you have examined
with other statistics available for consistency. The appropriate statistics vary
depending on the problem, but usually include load profile-related data in
V$SYSSTAT, operating system statistics, and so on. Perform cross-checks with
other data to confirm or refute the developing theory.
•
"Idle Wait Events" for the list of idle wait events
•
Oracle Database Reference for more information about wait events
Table of Wait Events and Potential Causes
Table 10-1 links wait events to possible causes and gives an overview of the Oracle data that
could be most useful to review next.
Table 10-1 Wait Events and Potential Cau

## 9. How to Use Hit Ratios and Wait Statistics
5
Measuring Database Performance
This chapter describes how to measure the performance of Oracle Database using database
statistics.
This chapter contains the following topics:
•
About Database Statistics
•
Interpreting Database Statistics
About Database Statistics
Database statistics provide information about the type of database load and the resources
being used by the database. To effectively measure database performance, statistics must be
available.
Oracle Database generates many types of cumulative statistics for the system, sessions,
segments, services, and individual SQL statements. Cumulative values for statistics are
generally accessible using dynamic performance views, or V$ views. When analyzing
database performance in any of these scopes, look at the change in statistics (delta value)
over the period you are interested in. Specifically, focus on the difference between the
cumulative values of a statistic at the start and the end of the period.
This section describes some of the more important database statistics that are used to
measure the performance of Oracle Database:
•
Time Model Statistics
•
Active Session History Statistics
•
Wait Events Statistics
•
Session and System Statistics
Oracle Database SQL Tuning Guide for information about optimizer statistics
Time Model Statistics
Time model statistics use time to identify quantitative effects about specific actions performed
on the database, such as logon operations and parsing. The most important time model
statistic is database time, or DB time. This statistic represents the total time spent in
database calls for foreground sessions and is an indicator of the total instance workload. DB
time is measured cumulatively from the time of instance startup and is calculated by
aggregating the CPU and wait times of all foreground sessions not waiting on idle wait events
(non-idle user sessions).
5-1
Note:
Because DB time is calculated by combining the times from all non-idle user
foreground sessions, it is possible that the DB time can exceed the actual
time elapsed after the instance started. For example, an instance that has
been running for 30 minutes could have four active user sessions whose
cumulative DB time is approximately 120 minutes.
When tuning an Oracle database, each component has its own set of statistics. To
look at the system as a whole, it is necessary to have a common scale for
comparisons. Many Oracle Database advisors and reports thus describe statistics in
terms of time.
Ultimately, the objective in tuning an Oracle database is to reduce the time that users
spend in performing an action on the database, or to simply reduce DB time. Time
model statistics are accessible from the V$SESS_TIME_MODEL and V$SYS_TIME_MODEL
views.
Oracle Database Reference for information about the V$SESS_TIME_MODEL
and V$SYS_TIME_MODEL views
Active Session History Statistics
Any session that is connected to the database and is waiting for an event that does not
belong to the Idle wait class is considered an active session. Oracle Database
samples active sessions every second and stores the sampled data in a circular buffer
in the shared global area (SGA).
The sampled session activity is accessible using the V$ACTIVE_SESSION_HISTORY view.
Each session sample contains a set of rows and the V$ACTIVE_SESSION_HISTORY view
returns one row for each active session per sample, starting with the latest session
sample rows. Because the active session samples are stored in a circular buffer in the
SGA, the greater the system activity, the smaller the number of seconds of session
activity that can be stored. This means that the duration for which a session sample is
displayed in the V$ view is completely dependent on the level of database activity.
Because the content of the V$ view can become quite large during heavy system
activity, only a portion of the session samples is written to disk.
By capturing only active sessions, a manageable set of data can be captured with its
size being directly related to the work being performed, rather than the number of
sessions allowed on the system. Active Session History (ASH) enables you to
examine and perform detailed analysis on both current data in the
V$ACTIVE_SESSION_HISTORY view and historical data in the
DBA_HIST_ACTIVE_SESS_HISTORY view, often avoiding the need to replay the workload
to trace additional performance information. ASH also contains execution plan
information for each captured SQL statement. You can use this information to identify
which part of SQL execution contributed most to the SQL elapsed time. The data
present in ASH can be rolled up in various dimensions that it captures, including:
•
SQL identifier of SQL statement
•
SQL plan identifier and hash value of the SQL plan used to execute the SQL statement
•
SQL execution plan information
•
Object number, file number, and block number
•
Wait event identifier and parameters
•
Session identifier and session serial number
•
Module and action name
•
Cli
