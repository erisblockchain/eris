#!/usr/bin/env python3

import testUtils

import argparse
import random
import subprocess
import signal

###############################################################
# Test for validating the dirty db flag sticks repeated nodeos restart attempts
###############################################################


Print=testUtils.Utils.Print

def errorExit(msg="", errorCode=1):
    Print("ERROR:", msg)
    exit(errorCode)

parser = argparse.ArgumentParser()
parser.add_argument("-v", help="verbose logging", action='store_true')
parser.add_argument("--leave-running", help="Leave cluster running after test finishes", action='store_true')
parser.add_argument("--dump-error-details",
                    help="Upon error print etc/eosio/node_*/config.ini and var/lib/node_*/stderr.log to stdout",
                    action='store_true')
parser.add_argument("--keep-logs", help="Don't delete var/lib/node_* folders upon test completion",
                    action='store_true')
parser.add_argument("--clean-run", help="Kill all nodeos and kleos instances", action='store_true')

args = parser.parse_args()
debug=args.v
pnodes=1
topo="mesh"
delay=1
chainSyncStrategyStr=testUtils.Utils.SyncResyncTag
total_nodes = pnodes
killCount=1
killSignal=testUtils.Utils.SigKillTag

killEosInstances= not args.leave_running
dumpErrorDetails=args.dump_error_details
keepLogs=args.keep_logs
killAll=args.clean_run

seed=1
testUtils.Utils.Debug=debug
testSuccessful=False

def runNodeosAndGetOutput(myNodeId, myTimeout=3):
    """Startup nodeos, wait for timeout (before forced shutdown) and collect output. Stdout, stderr and return code are returned in a dictionary."""
    Print("Launching nodeos process id: %d" % (myNodeId))
    cmd="programs/nodeos/nodeos --config-dir etc/eosio/node_bios --data-dir var/lib/node_bios"
    Print("cmd: %s" % (cmd))
    proc=subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    output={}
    try:
        outs,errs = proc.communicate(timeout=myTimeout)
        output["stdout"] = outs.decode("utf-8")
        output["stderr"] = errs.decode("utf-8")
        output["returncode"] = proc.returncode
    except (subprocess.TimeoutExpired) as _:
        Print("ERROR: Nodeos is running beyond the defined wait time. Hard killing nodeos instance.")
        proc.send_signal(signal.SIGKILL)
        return (False, None)

    return (True, output)

random.seed(seed) # Use a fixed seed for repeatability.
cluster=testUtils.Cluster(walletd=True)

try:
    cluster.setChainStrategy(chainSyncStrategyStr)

    cluster.killall(allInstances=killAll)
    cluster.cleanup()

    Print ("producing nodes: %d, topology: %s, delay between nodes launch(seconds): %d, chain sync strategy: %s" % (
        pnodes, topo, delay, chainSyncStrategyStr))

    Print("Stand up cluster")
    if cluster.launch(pnodes, total_nodes, topo=topo, delay=delay, dontBootstrap=True) is False:
        errorExit("Failed to stand up eos cluster.")

    node=cluster.getNode(0)
    if node is None:
        errorExit("Cluster in bad state, received None node")

    Print("Kill cluster nodes.")
    cluster.killall(allInstances=killAll)
    
    Print("Restart nodeos repeatedly to ensure dirty database flag sticks.")
    nodeId=0
    timeout=3
    
    for i in range(0,3):
        Print("Attempt %d." % (i))
        ret = runNodeosAndGetOutput(nodeId, timeout)
        assert(ret)
        assert(isinstance(ret, tuple))
        if not ret or not ret[0]:
            exit(1)

        assert(ret[1])
        assert(isinstance(ret[1], dict))
        # pylint: disable=unsubscriptable-object
        stderr= ret[1]["stderr"]
        retCode=ret[1]["returncode"]
        assert(retCode == 2)
        assert("database dirty flag set" in stderr)

    testSuccessful=True
finally:
    if testSuccessful:
        Print("Test succeeded.")
    else:
        Print("Test failed.")

    if not testSuccessful and dumpErrorDetails:
        cluster.dumpErrorDetails()
        Print("== Errors see above ==")

    if killEosInstances:
        Print("Shut down the cluster.")
        cluster.killall(allInstances=killAll)
        if testSuccessful and not keepLogs:
            Print("Cleanup cluster data.")
            cluster.cleanup()

exit(0)
