"""
NETLIST.py - Netlist traversing functions
"""

import copy

def load_asc_netlist( filename ):
    """
    load_asc_netlist( filename )

    Load ASC netlist file "filename" into dictionary:
            *PART*
            Ref Type
            Ref Type
            Ref Type

            *CONNECTION*
            *SIGNAL* Name
            Ref Ref
            Ref Ref
            Ref Ref

            *MISC*
            Ignored

            *END*

    Text file is processed line by line.
        Blank lines are ignored.
        Lines after *MISC* are ignored.

    Returned dictionary contains 2 sub-dictionaries:
        ["PART"] = { Ref: Type, ... }, and
        ["CONNECTION"] = { Signal: [ Ref.Pin, ... ], ... }
        ["REF.PIN"] = { Ref.Pin: Signal, ... }
        ["PINS"] = { Ref: [Pins, ... ] }
        ["RAIL"] = { Signal: Voltage, ... }
    """
    netlist_dict = { "PART": {}, "CONNECTION": {}, "REF.PIN": {}, "RAIL": {}, "PINS": {} }
    sub_dict = ""
    signal_name = ""
    new_signal = False
    done = False

    print "Loading netlist"
    print filename

    try:
        f = open( filename, "r" )
        s = f.readline()
        while len( s ) > 0 and not done:
            ss = s.strip()
            ##print ss
            if len( ss ) > 0:
                if ss[0] == "*":
                    if ss == "*PART*":
                        sub_dict = "PART"
                        print "Loading parts"
                    elif ss == "*CONNECTION*":
                        sub_dict = "CONNECTION"
                        print "Loading connections"
                    elif ss == "*MISC*":
                        print "Done"
                        done = True
                    elif sub_dict == "CONNECTION" and ss[0:8] == "*SIGNAL*":
                        ss_token = ss.split( " ")
                        signal_name = ss_token[1]
                        netlist_dict[sub_dict][signal_name] = []
                        new_signal = True
                        ##print "Connections for %s" % signal_name
                        
                        # Check if signal is possibly a rail signal. Can be a rail if starts with "+" or has an initial format of
                        # P(some_number)V, for example if the signal name is P3V3_DMD, the name P3V will flag this signal as a possible rail
                        # and will eventually get translated to 3.3V later
                        possible_rail = signal_name[0] == "+"
                        if possible_rail != True:
                            if signal_name[0] == "P" and signal_name[1].isdigit():
                                initial_num = ""
                                for n in signal_name[1:]:
                                    if n.isdigit():
                                        initial_num += n
                                    elif n.upper() == "V": 
                                        possible_rail = len(initial_num) > 0
                                        break
                      
                        # Check if signal is rail
                        if possible_rail:
                            num_string = ""
                            name_part = "UNITS"
                            rail_voltage = 0.0
                            for c in signal_name[1:]:
                                if c.isdigit():
                                    num_string += c
                                elif c.upper() == "V" and name_part == "UNITS":
                                    num_string += "."
                                    name_part = "DECIMALS"
                                else:
                                    try:
                                        rail_voltage = float( num_string )
                                    except:
                                        rail_voltage = 0.0
                                    ##print "%s -> %g" % ( num_string, rail_voltage )
                                    num_string = ""
                                    break

                            if len( num_string ) > 0:
                                try:
                                    rail_voltage = float( num_string )
                                except:
                                    rail_voltage = 0.0
                                ##print "%s -> %g" % ( num_string, rail_voltage )
                                num_string = ""
                                
                            netlist_dict["RAIL"][signal_name] = rail_voltage

                        elif signal_name[0:4] == "GND":
                            netlist_dict["RAIL"][signal_name] = 0.0
                    
                else:
                    ss_token = ss.split( " " )
                    if sub_dict == "PART":
                        if len( ss_token ) > 1:
                            netlist_dict[sub_dict][ss_token[0]] = ss_token[1]
                    elif sub_dict == "CONNECTION":
                        ## print new_signal
                        ## print ss_token
                        if len( ss_token ) > 1:
                            ( ref, pin ) = ss_token[1].split('.')
                            if ref not in netlist_dict["PINS"]:
                                netlist_dict["PINS"][ref] = []
                            netlist_dict[sub_dict][signal_name].append( ss_token[1] )
                            netlist_dict["REF.PIN"][ss_token[1]] = signal_name
                            netlist_dict["PINS"][ref].append(pin)
                        if new_signal:
                            ( ref, pin ) = ss_token[0].split('.')
                            if ref not in netlist_dict["PINS"]:
                                netlist_dict["PINS"][ref] = []
                            netlist_dict[sub_dict][signal_name].append( ss_token[0] )
                            netlist_dict["REF.PIN"][ss_token[0]] = signal_name
                            netlist_dict["PINS"][ref].append(pin)
                            new_signal = False
                        ## print netlist_dict[sub_dict][signal_name]
                        ## print netlist_dict["REF.PIN"]

            s = f.readline()

        f.close()
    except Exception, e:
        print e
        pass

    ##print netlist_dict

    return ( netlist_dict )

class netlist():

    def load_syscon_csv( filename ):
        """
        load_syscon_csv( filename )

        Load CSV file containing system connection data

        CSV file contains different data sections as determined by first column
            Blank line      Ignored
            COMMENT         Rest of line ignored
            NETLIST         Filename of netlist - ID, FILENAME
            DESIRED         Desired connection - FROM ID, FROM SIGNAL, TO ID, TO SIGNAL
            HARNESSID       Beginning of harness description - HARNESS_ID
                            Must be followed by HARNESSPIN lines
            HARNESSPIN      Harness pin information - REF1, PIN, REF2, PIN
                            Pins may be specified in any order
            DEVICE          Device pin information - TYPE, PIN, PIN [, BIDIR]
                            If BIDIR is non-blank, device connection is assumed bi-directional
            CONNECTION      Indicates physical connection - FROM ID, FROM REF, TO ID, TO REF
                            Connection will be pin for pin (straight-through)
            CONNECTOR       Indicates connector shape data - ID, REF, ROWS, COLS
            

        Returns dictionary as follows:
            ["NETLIST_FILE"] = { ID: Filename, ID: Filename, ... }
            ["NETLIST"] = refer to load_asc_netlist
            ["DESIRED"] = { ID.Signal: ID.Signal, ... }
            ["HARNESS"] = { ID: { Ref.Pin: Ref.Pin, ... }, ID: { }, ... }
            ["CONNECTION"] = { ID.Ref: ID.Ref, ... }
            ["CONNECTOR"] = { ID.Ref: { "Rows": Rows, "Cols": Cols }, ... }
            ["DEVICE"] = { Type: { Ref.Pin: Ref.Pin, ... } }

        """

        syscon_dict = {}
        syscon_dict["NETLIST_FILE"] = {}
        syscon_dict["NETLIST"] = {}
        syscon_dict["DESIRED"] = {}
        syscon_dict["HARNESS"] = {}
        syscon_dict["CONNECTION"] = {}
        syscon_dict["CONNECTOR"] = {}
        syscon_dict["DEVICE"] = {}

        harness_id = ""
        harness_defined = False

        print "Loading netlist"
        print filename

        done = False
        try:
            f = open( filename, "r" )
            s = f.readline()
            while len( s ) > 0 and not done:
                ss = s.strip()
                ss_token = ss.split( "," )
                ##print ss
                if len( ss ) > 0 and ss_token[0] != "COMMENT":
                    if ss_token[0] == "NETLIST" and len( ss_token ) > 2:
                        id = ss_token[1]
                        syscon_dict["NETLIST_FILE"][id] = ss_token[2]
                        ( netlist ) = load_asc_netlist( ss_token[2] )
                        syscon_dict["NETLIST"][id] = netlist
                    elif ss_token[0] == "DESIRED" and len( ss_token ) > 4:
                        from_id_signal = "%s.%s" % ( ss_token[1], ss_token[2] )
                        to_id_signal = "%s.%s" % ( ss_token[3], ss_token[4] )
                        syscon_dict["DESIRED"][from_id_signal] = to_id_signal
                    elif ss_token[0] == "HARNESSID" and len( ss_token ) > 1:
                        harness_id = ss_token[1]
                        syscon_dict["HARNESS"][harness_id] = {}
                        harness_defined = True
                    elif ss_token[0] == "HARNESSPIN" and len( ss_token ) > 4:
                        if not harness_defined:
                            print "Need to define harness using HARNESSID line before defining pins"
                        else:
                            from_ref_pin = "%s.%s" % ( ss_token[1], ss_token[2] )
                            to_ref_pin = "%s.%s" % ( ss_token[3], ss_token[4] )
                            # Need to put in connection "both ways"
                            syscon_dict["HARNESS"][harness_id][from_ref_pin] = to_ref_pin
                            syscon_dict["HARNESS"][harness_id][to_ref_pin] = from_ref_pin
                    elif ss_token[0] == "CONNECTION" and len( ss_token ) > 4:
                        from_id_ref = "%s.%s" % ( ss_token[1], ss_token[2] )
                        to_id_ref = "%s.%s" % ( ss_token[3], ss_token[4] )
                        # Need to put in connection "both ways"
                        syscon_dict["CONNECTION"][from_id_ref] = to_id_ref
                        syscon_dict["CONNECTION"][to_id_ref] = from_id_ref
                    elif ss_token[0] == "CONNECTOR" and len( ss_token ) > 4:
                        id_ref = "%s.%s" % ( ss_token[1], ss_token[2] )
                        syscon_dict["CONNECTOR"][id_ref] = { "Rows": ss_token[3], "Cols": ss_token[4] }
                    elif ss_token[0] == "DEVICE" and len( ss_token ) > 3:
                        if ss_token[1] not in syscon_dict["DEVICE"]:
                            syscon_dict["DEVICE"][ss_token[1]] = { ss_token[2]: ss_token[3] }
                            
                        syscon_dict["DEVICE"][ss_token[1]][ss_token[2]] = ss_token[3]
                        if len( ss_token ) > 4 and len( ss_token[4] ) > 0:
                            syscon_dict["DEVICE"][ss_token[1]][ss_token[3]] = ss_token[2]
                else:
                    print ss

                s = f.readline()
                
            f.close()
            
        except Exception, e:
            print e
            pass

        return ( syscon_dict )
        

    def trace_netlist_signal( syscon_dict, from_id_signal, to_id_signal, path ):
        """
        trace_netlist_signal

        Locate all connectors attached to a netlist signal and call
            trace_connection to see if they connect to the destination signal
        """
        
        print "trace_netlist_signal( %s, %s )" % ( from_id_signal, to_id_signal )
        print path
        
        trace_success = False
        from_token = from_id_signal.split( '.' )
        to_token = from_id_signal.split( '.' )
        valid_params = True
        if len( from_token ) > 1:
            from_id = from_token[0]
            from_signal = from_token[1]
        else:
            valid_params = False

        if len( to_token ) > 1:
            to_id = to_token[0]
            to_signal = to_token[1]
        else:
            valid_params = False

        if from_id_signal == to_id_signal:
            print "\n***\n\n*** SUCCESS\n\n"
            trace_success = True
        elif valid_params:
            trace_success = False
            if from_id in syscon_dict["NETLIST"]:
                if from_signal in syscon_dict["NETLIST"][from_id]["CONNECTION"]:
                    for ref_pin in syscon_dict["NETLIST"][from_id]["CONNECTION"][from_signal]:
                        if ref_pin[0] == "J" or ref_pin[0] == "P":
                            path_id = "%s.%s" % ( from_id, ref_pin )
                            # Don't follow a path we've been down before
                            if path_id not in path:                            
                                test_path = copy.copy( path )
                                test_path.append( path_id )
                                ( id_signal, test_path ) = trace_connection( syscon_dict, from_id, ref_pin, test_path )
                                if len( id_signal ) > 0:
                                    ##print "Looking for path from %s to %s" % ( id_signal, to_id_signal )
                                    ( trace_success, test_path ) = trace_netlist_signal( syscon_dict, id_signal, to_id_signal, test_path )
                        else:
                            ref_token = ref_pin.split( '.' )
                            ref_type = syscon_dict["NETLIST"][from_id]["PART"][ref_token[0]]
                            path_id = "%s.%s" % ( from_id, ref_pin )
                            # Don't follow a path we've been down before
                            if ref_type in syscon_dict["DEVICE"] and path_id not in path:
                                test_path = copy.copy( path )
                                test_path.append( path_id )
                                ( id_signal, test_path ) = trace_device( syscon_dict, from_id, ref_pin, ref_type, test_path )
                                if len( id_signal ) > 0:
                                    ##print "Looking for path from %s to %s" % ( id_signal, to_id_signal )
                                    ( trace_success, test_path ) = trace_netlist_signal( syscon_dict, id_signal, to_id_signal, test_path )
                        if trace_success:
                            path = test_path
                            break

        return ( trace_success, path )


    def trace_connection( syscon_dict, from_id, from_ref_pin, path ):
        """
        Returns id_signal at end of connection

        Will trace through harnesses until it gets to a signal name in a netlist
        """

        ##print "trace_connection( %s.%s )" % ( from_id, from_ref_pin )
        ##print path
        
        to_id_signal = ""
        from_token = from_ref_pin.split( '.' )
        valid_params = True
        if len( from_token ) > 1:
            from_ref = from_token[0]
            from_pin = from_token[1]
        else:
            valid_params = False

        if valid_params:
            from_id_ref = "%s.%s" % ( from_id, from_ref )
            if from_id_ref in syscon_dict["CONNECTION"]:
                to_id_ref = syscon_dict["CONNECTION"][from_id_ref]
                to_token = to_id_ref.split( '.' )
                if len( to_token ) > 1:
                    to_id = to_token[0]
                    to_ref = to_token[1]
                # Pins are always the same on either side of a connection
                to_ref_pin = "%s.%s" % ( to_ref, from_pin )
                
                ##print "%s connected to %s" % ( from_id_ref, to_id_ref )

                # Check to see if connection is to harness
                if to_id in syscon_dict["HARNESS"]:
                    ##print "%s is a harness, looking for %s" % ( to_id, to_ref_pin )
                    ##print syscon_dict["HARNESS"][to_id]
                    if to_ref_pin in syscon_dict["HARNESS"][to_id]:
                        connected_ref_pin = syscon_dict["HARNESS"][to_id][to_ref_pin]
                        path.append( "%s.%s" % ( to_id, to_ref_pin ) )
                        path.append( "%s.%s" % ( to_id, connected_ref_pin ) )
                        
                        ##print "%s is connected to %s" % ( to_id_ref, connected_ref_pin )
                        ( to_id_signal, path ) = trace_connection( syscon_dict, to_id, connected_ref_pin, path )

                # Otherwise connection should be to netlist
                elif to_id in syscon_dict["NETLIST"]:
                    ##print "%s is a PCB, looking for %s" % ( to_id, to_ref_pin )
                    ##print syscon_dict["NETLIST"][to_id]
                    if to_ref_pin in syscon_dict["NETLIST"][to_id]["REF.PIN"]:
                        path.append( "%s.%s" % ( to_id, to_ref_pin ) )
                        to_signal = syscon_dict["NETLIST"][to_id]["REF.PIN"][to_ref_pin]
                        to_id_signal = "%s.%s" % ( to_id, to_signal )
                        ##print "%s connected to %s" % ( to_ref_pin, to_id_signal )

        return ( to_id_signal, path )

        
    def trace_device( syscon_dict, from_id, from_ref_pin, from_ref_type, path ):
        """
        Returns id_signal at end of device

        Will trace through device
        """

        ##print "trace_device( %s.%s, %s )" % ( from_id, from_ref_pin, from_ref_type )
        ##print path
        
        valid_params = True
        to_id_signal = ""

        from_token = from_ref_pin.split( '.' )
        if len( from_token ) > 1:
            from_ref = from_token[0]
            from_pin = from_token[1]
        else:
            valid_params = False
        
        ##print "Checking %s pin %s" % ( from_ref, from_pin )
        
        if valid_params:
            if from_pin in syscon_dict["DEVICE"][from_ref_type]:
                to_pin = syscon_dict["DEVICE"][from_ref_type][from_pin]
                to_ref_pin = "%s.%s" % ( from_ref, to_pin )
            
                ##print "%s connected to %s" % ( from_ref_pin, to_ref_pin )

                if from_id in syscon_dict["NETLIST"]:
                    if to_ref_pin in syscon_dict["NETLIST"][from_id]["REF.PIN"]:
                        path.append( "%s.%s" % ( from_id, to_ref_pin ) )
                        to_signal = syscon_dict["NETLIST"][from_id]["REF.PIN"][to_ref_pin]
                        to_id_signal = "%s.%s" % ( from_id, to_signal )
                        ##print "%s connected to %s" % ( to_ref_pin, to_id_signal )

        return ( to_id_signal, path )



    

def main():

    print "NETLIST.py: Netlist functions"

    ( test ) = load_syscon_csv( "syscon.csv" )
    ##print test["DEVICE"]
    
    for desired in test["DESIRED"]:
        from_signal = desired
        to_signal = test["DESIRED"][from_signal]
        
        path = []
        ( flag, path ) = trace_netlist_signal( test, from_signal, to_signal, path )
        print "%s -> %s" % ( from_signal, to_signal )
        print flag
        print path



if __name__ == "__main__":
    main()


# vi:set shiftwidth=4 tabstop=4:
# vim:set expandtab list lcs=tab\:>>:

