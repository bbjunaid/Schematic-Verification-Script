"""
SYSTEM_CONNECTIONS.py - Netlist traversing functions

TO DO

Add pin fanout through harness capability

Add check that all refvolt signals are at correct voltage (to verify internal connections)
Add refsig and pin definition file generation

Revamp REFVOLT and DEVICEPULL data order to allow specification of multiple pins
Add DEVICEVOLT?
Revamp DEVICELINK to allow

Differentiate between harness types and harness instantiations? (eg. SAS)?

Add termination detection

Add comparison to previous analysis to detect changes
"""

import sys
import getopt
import copy

import netlist

class system_connections():
    def __init__( self ):
        self.syscon_dict = {}

    def load_syscon_csv( self, filename ):
        """
        load_syscon_csv( filename )

        Load CSV file containing system connection data

        CSV file contains different data sections as determined by first column
            Blank line      Ignored
            COMMENT         Rest of line ignored
            NETLIST         Filename of netlist - ID, FILENAME
            DESIRED         Desired connection - FROM ID, FROM SIGNAL / REF.PIN, TO ID, TO SIGNAL / REF.PIN
            HARNESSLINK     Harness link information - ID, REF1, PIN, REF2, PIN
                            Pins may be specified in any order
            DEVICELINK      Device link information - TYPE, PIN, PIN [, BIDIR [, VOLT, VOLT ] ]
                            If BIDIR is non-blank, device connection is assumed bi-directional
            DEVICEPIN       Device pin information - two options
                                TYPE, RC, ROWS, COLS, DIR
                                    Rectangular pin layout ROWS x COLS, DIR specifies
                                    pin 1 location (TL, TR, BL, BR) and direction of
                                    increase (H, V)
                                        eg TLH = pin 1 top-left (row 1 col 1),
                                                    pin 2 beside it (row 1 col 2)
                                        eg TLV = pin 1 top-left (row 1 col 1),
                                                    pin 2 below it (row 2 col 1)
                                TYPE, ARB, ROW, COL, PIN
                                    Arbitrary pin layout, PIN @ ROW, COL
                                    Specify each pin in layout
                                TYPE, CATEGORY, NAME,  PIN1, PIN2, PIN3, ...
                                    Specifies pins to be under a certain category of type NAME. Outputs
                                    the device pinout in one column with the with the signals
                                    arranged by category NAME. Category NAME appears beside. Eg:
                                    BANK 0    Signal1
                                              Signal2
                                              Signal3...
                                    BANK 1    Signal4...
            CONNECTION      Indicates physical connection - FROM ID, FROM REF, TO ID, TO REF
                            Connection will be pin for pin (straight-through)
            MAP             Indicates MAP sequence in output file - ID, REF, NAME
                            If comments appear between MAP entries they will be copied
                            to output file
            RAIL            Indicates that a certain signal name is a rail
            IGNORE          Specifies Signal Name or Device to ignore. When used on signal name, it outputs a TRUE for
                            the IGNORE FLAG (see gen_check_line). When specified on device, it does not go through the device
                            or check it for voltage pulls.
            REFSIG          Associate an internal schematic signal on a device refdes to the external name used elsewhere. Can specify
                            a voltage standard on that signal.
            DEVICEPARAM     Characterize devices with additional parameters such as manufacturer name, etc.


        Returns dictionary as follows:
            ["COMMNETS"] = { $$##__COMMENTn: String, ... }
            ["NETLIST_FILE"] = { ID: Filename, ID: Filename, ... }
            ["NETLIST"] = {ID:{...}, ... }
            ["CHECKTRACE"] = [ ( ID.Signal or ID.Ref.Pin, ID.Signal or ID.Ref.Pin, { "GROUP": Group, "VOLT": Volt } ) or ( $$##__COMMENTn, $$##__COMMENTn ), ... ]
            ["HARNESS"] = { ID: { Ref.Pin: Ref.Pin, ... }, ID: { }, ... }
            ["HARNESS_SEQ"] = [ ID or $$##__COMMENTn, ... ]
            ["CONNECTION"] = { ID.Ref: ID.Ref, ... }
            ["CONNECTION_REFS"] = { ID: [ Ref, ... ], ... }
            ["MAP"] = { ID.Ref: Name, ... }
            ["MAP_SEQ"] = [ ID.Ref or $$##__COMMENTn, ... ]
            ["DEVICEMAP"] = { ID.Ref: Name, ... }
            ["DEVICE"] = { Type: { Ref.Pin: Ref.Pin, ... } }
            ["DEVICEPULL"] = { Type: { Ref.Pin: Ref.Pin, ... } }
            ["DEVICEVOLT"] = { Type: { Ref.Pin: Volt, ... } }
            ["DEVICEPIN"] = { Type: { "Rows": n, "Cols": m, "Map": { Row-Col: Pin, ... }, "Category": { Name: [Pin,...], ... } }
            ["REFVOLT"] = { ID.Ref.Pin: Volt, ... }
            ["IGNORE"] = { "SIGNAL":[ID.Signal,...], "DEVICE": [Device,...] }
            ["REFSIG"] = { ID.Ref: [ (Pin, Internal Signal, External Signal, IO Standard), ... ], ...  }
            ["DEVICEPARAM"] = { Type: { PARAM: Param Value, ... } }


        NETLIST:
        Returned dictionary contains 2 sub-dictionaries:
        ["PART"] = { Ref: Type, ... }, and
        ["CONNECTION"] = { Signal: [ Ref.Pin, ... ], ... }
        ["REF.PIN"] = { Ref.Pin: Signal, ... }
        ["RAIL"] = { Signal: Voltage, ... }
        ["REF"] = [ Pin, ... ]
        """

        for subdict in [ "COMMENTS", "NETLIST_FILE", "NETLIST", "HARNESS", "CONNECTION", "CONNECTION_REFS", "MAP", "DEVICEMAP", "DEVICE", "DEVICEPIN", \
                        "DEVICEPULL", "DEVICEVOLT", "REFVOLT", "IGNORE", "REFSIG", "DEVICEPARAM" ]:
            if subdict not in self.syscon_dict:
                self.syscon_dict[subdict] = {}

        for sublist in [ "CHECKTRACE", "CHECKVOLT", "HARNESS_SEQ", "MAP_SEQ", "IMPORT" ]:
            if sublist not in self.syscon_dict:
                self.syscon_dict[sublist] = []

        self.syscon_dict["IGNORE"]["SIGNAL"] = []
        self.syscon_dict["IGNORE"]["DEVICE"] = []

        print "Loading system connection data from %s" % filename

        comment_number = 0
        comment_id = ""
        comment_string = ""
        comment_flag = False
        done = False
        try:
            f = open( filename, "r" )
            s = f.readline()
            while len( s ) > 0 and not done:
                ss = s.strip()
                # Remove any trailing cosmmas as CSV files often pad to common width
                ss = ss.rstrip( ',' )
                ss_token = ss.split( "," )
                for i in range( len( ss_token ) ):
                    ss_token[i] = ss_token[i].strip()
                ##print ss
                ##print ss_token
                # Ignore blank lines
                if len( ss ) > 0:
                    ss_processed = False
                    if ss_token[0] == "":
                        # Blank line or blank first column
                        ss_processed = True

                    if ss_token[0] == "COMMENT":
                        # COMMENT, Arbitrary string
                        comment_string += ss[8:] + "\n"
                        comment_flag = True
                        ss_processed = True

                    if ss_token[0] != "COMMENT" and comment_flag and len( comment_string ) > 0:
                        # If we're at the end of a block of comments
                        comment_number += 1
                        comment_id = "$$##__COMMENT%d" % comment_number

                        self.syscon_dict["COMMENTS"][comment_id] = comment_string
                        comment_string = ""
                        ss_processed = True

                    if ss_token[0] == "IMPORT" and len( ss_token ) > 1:
                        # IMPORT, FILENAME
                        import_filename = ss_token[1]
                        if import_filename not in self.syscon_dict["IMPORT"]:
                            ##print self.syscon_dict
                            print "Importing %s" % import_filename
                            self.load_syscon_csv( import_filename )
                            self.syscon_dict["IMPORT"].append(import_filename)
                            ##print self.syscon_dict

                    elif ss_token[0] == "NETLIST" and len( ss_token ) > 2:
                        # NETLIST, ID, FILENAME
                        id = ss_token[1]
                        self.syscon_dict["NETLIST_FILE"][id] = ss_token[2]
                        ( net ) = netlist.load_asc_netlist( ss_token[2] )
                        self.syscon_dict["NETLIST"][id] = net

                    elif ss_token[0] == "RAIL" and len( ss_token ) > 3:
                        # RAIL, ID, SIGNAL, value
                        if ss_token[1] in self.syscon_dict["NETLIST"] and ss_token[2] in self.syscon_dict["NETLIST"][ss_token[1]]["CONNECTION"]:
                            try:
                                rail_voltage = float( ss_token[3] )
                            except:
                                rail_voltage = 0.0
                            self.syscon_dict["NETLIST"][ss_token[1]]["RAIL"][ss_token[2]] = rail_voltage

                    elif ss_token[0] == "IGNORE" and len( ss_token ) > 3:
                        # IGNORE, ID, SIGNAL/DEVICE, Signal Name/Device Name
                        ( id, ignore_type, param ) = ( ss_token[1], ss_token[2], ss_token[3] )

                        if id in self.syscon_dict["NETLIST"]:
                            if ignore_type == "SIGNAL" and param in self.syscon_dict["NETLIST"][ss_token[1]]["CONNECTION"]:
                                id_signal = "%s.%s" % ( id, param )
                                self.syscon_dict["IGNORE"]["SIGNAL"].append(id_signal)
                            elif ignore_type == "DEVICE":
                                self.syscon_dict["IGNORE"]["DEVICE"].append( param )

                    elif ss_token[0] == "CHECKTRACE" and len( ss_token ) > 4:
                        # CHECKTRACE, FROM ID, FROM SIG/REF, TO ID, TO SIG/REF [, GROUP [, VOLT ]]
                        from_id_signal = "%s.%s" % ( ss_token[1], ss_token[2] )
                        to_id_signal = "%s.%s" % ( ss_token[3], ss_token[4] )
                        from_to_id_signal = "%s.%s" % ( from_id_signal, to_id_signal )
                        print "Decoding CHECKTRACE %s -> %s" % ( from_id_signal, to_id_signal )
                        # If there were comments prior to this desired link, note them in the sequence list
                        if comment_flag:
                            self.syscon_dict["CHECKTRACE"].append( ( comment_id, comment_id, {} ) )
                            comment_flag = False

                        check_dict = {}

                        if len( ss_token ) > 5:
                            check_dict["GROUP"] = ss_token[5]

                        if len( ss_token ) > 6:
                            try:
                                check_volt = float( ss_token[6] )
                                check_dict["VOLT"] = float( ss_token[6] )
                            except:
                                pass

                        self.syscon_dict["CHECKTRACE"].append( ( from_id_signal, to_id_signal, check_dict ) )

                    elif ss_token[0] == "CHECKVOLT" and len( ss_token ) > 2:
                        # CHECKVOLT, ID, SIG/REF, [, GROUP [, VOLT ]]
                        id_signal = "%s.%s" % ( ss_token[1], ss_token[2] )
                        # If there were comments prior to this desired link, note them in the sequence list
                        if comment_flag:
                            self.syscon_dict["CHECKVOLT"].append( ( comment_id, {} ) )
                            comment_flag = False

                        check_dict = {}

                        if len( ss_token ) > 3:
                            check_dict["GROUP"] = ss_token[3]

                        if len( ss_token ) > 4:
                            try:
                                desired_volt = float( ss_token[4] )
                                check_dict["VOLT"] = float( ss_token[4] )
                            except:
                                pass

                        print "Decoding CHECKVOLT %s %s" % ( id_signal, check_dict )
                        self.syscon_dict["CHECKVOLT"].append( ( id_signal, check_dict ) )

                    elif ss_token[0] == "HARNESSLINK" and len( ss_token ) > 5:
                        # HARNESSLINK, ID, REF1, PIN1, REF2, PIN2
                        from_ref_pin = "%s.%s" % ( ss_token[2], ss_token[3] )
                        to_ref_pin = "%s.%s" % ( ss_token[4], ss_token[5] )
                        ##print "%s: %s -> %s" % ( ss_token[1], from_ref_pin, to_ref_pin )
                        if ss_token[1] not in self.syscon_dict["HARNESS"]:
                            self.syscon_dict["HARNESS"][ss_token[1]] = {}
                        # Need to put in connection "both ways"
                        self.syscon_dict["HARNESS"][ss_token[1]][from_ref_pin] = to_ref_pin
                        self.syscon_dict["HARNESS"][ss_token[1]][to_ref_pin] = from_ref_pin
                        if ss_token[1] not in self.syscon_dict["HARNESS_SEQ"]:
                            # If there were comments prior to this harness, note them in the sequence list
                            if comment_flag:
                                self.syscon_dict["HARNESS_SEQ"].append( comment_id )
                                comment_flag = False
                            self.syscon_dict["HARNESS_SEQ"].append( ss_token[1] )

                    elif ss_token[0] == "CONNECTION" and len( ss_token ) > 4:
                        # CONNECTION, FROM ID, FROM REF, TO ID, TO REF
                        from_id = ss_token[1]
                        from_ref = ss_token[2]
                        to_id = ss_token[3]
                        to_ref = ss_token[4]
                        from_id_ref = "%s.%s" % ( from_id, from_ref )
                        to_id_ref = "%s.%s" % ( to_id, to_ref )
                        # Need to put in connection "both ways"
                        self.syscon_dict["CONNECTION"][from_id_ref] = to_id_ref
                        self.syscon_dict["CONNECTION"][to_id_ref] = from_id_ref

                        if from_id not in self.syscon_dict["CONNECTION_REFS"]:
                            self.syscon_dict["CONNECTION_REFS"][from_id] = []
                        if to_id not in self.syscon_dict["CONNECTION_REFS"]:
                            self.syscon_dict["CONNECTION_REFS"][to_id] = []
                        if from_ref not in self.syscon_dict["CONNECTION_REFS"][from_id]:
                            self.syscon_dict["CONNECTION_REFS"][from_id].append( from_ref )
                        if to_ref not in self.syscon_dict["CONNECTION_REFS"][to_id]:
                            self.syscon_dict["CONNECTION_REFS"][to_id].append( to_ref )

                    elif ss_token[0] == "MAP" and len( ss_token ) > 3:
                        # MAP, ID, REF, NAME
                        id_ref = "%s.%s" % ( ss_token[1], ss_token[2] )
                        self.syscon_dict["MAP"][id_ref] = ss_token[3]
                        # If there were comments prior to this map, note them in the sequence list
                        if comment_flag:
                            self.syscon_dict["MAP_SEQ"].append( comment_id )
                            comment_flag = False
                        self.syscon_dict["MAP_SEQ"].append( id_ref )

                    elif ss_token[0] == "DEVICELINK" and len( ss_token ) > 3:
                        # DEVICELINK, TYPE, PIN, PIN [, BIDIR [, VOLT, VOLT]]
                        if ss_token[1] not in self.syscon_dict["DEVICE"]:
                            # If device didn't exist, create it
                            self.syscon_dict["DEVICE"][ss_token[1]] = { ss_token[2]: ss_token[3] }

                        self.syscon_dict["DEVICE"][ss_token[1]][ss_token[2]] = ss_token[3]
                        if len( ss_token ) > 4 and len( ss_token[4] ) > 0:
                            # If link is bidirectional, put in reverse connection
                            self.syscon_dict["DEVICE"][ss_token[1]][ss_token[3]] = ss_token[2]

                        if len( ss_token ) > 6:
                            try:
                                volt1 = float( ss_token[5] )
                                volt2 = float( ss_token[6] )
                                # If pin voltages specified, note them
                                if ss_token[1] not in self.syscon_dict["DEVICEVOLT"]:
                                    # If device didn't exist, create it
                                    self.syscon_dict["DEVICEVOLT"][ss_token[1]] = { }
                                self.syscon_dict["DEVICEVOLT"][ss_token[1]][ss_token[2]] = volt1
                                self.syscon_dict["DEVICEVOLT"][ss_token[1]][ss_token[3]] = volt2
                            except:
                                pass

                    elif ss_token[0] == "REFSIG" and len( ss_token ) > 5:
                        # REFSIG, ID, REF, PIN, INT SIGNAL, EXT SIGNAL [,IOSTANDARD]
                        io_standard = "NA"
                        if len ( ss_token ) > 6:
                            io_standard = ss_token[6]
                        ( id, ref ) = ( ss_token[1], ss_token[2] )
                        id_ref = "%s.%s" % (id,ref)
                        if id_ref not in self.syscon_dict["REFSIG"]:
                            self.syscon_dict["REFSIG"][id_ref] = []
                        self.syscon_dict["REFSIG"][id_ref].append( (ss_token[3], ss_token[4], ss_token[5], io_standard) )

                    elif ss_token[0] == "DEVICEPARAM" and len( ss_token ) > 3:
                        # DEVICEPARAM, TYPE, PARAM_1, PARAM_1_VALUE [,PARAM2, PARAM_2_VALUE, ...]
                        type= ss_token[1]
                        if type not in self.syscon_dict["DEVICEPARAM"]:
                            self.syscon_dict["DEVICEPARAM"][type] = {}
                            for i, param in enumerate(ss_token[2:],start=2):
                                # only look at even indices which will have parameter type and odd indices with corresponding value
                                if i%2 == 0:
                                    self.syscon_dict["DEVICEPARAM"][type][param] = ss_token[i+1]

                    elif ss_token[0] == "DEVICEPULL" and len( ss_token ) > 3:
                        # DEVICEPULL, TYPE, [# A], DIR, PIN [, PIN [, ... ]], PIN [, PIN [, ... ]]
                        num_a = 1
                        a_location = 3
                        if ss_token[2].isdigit():
                            num_a = int(ss_token[2])
                            ss_dir = ss_token[3]
                            a_location = 4
                        else:
                            ss_dir = ss_token[2]

                        if ss_token[1] not in self.syscon_dict["DEVICEPULL"]:
                            # If device didn't exist, create it
                            self.syscon_dict["DEVICEPULL"][ss_token[1]] = { }

                        for ss_a in ss_token[a_location:a_location+num_a]:
                            for ss_b in ss_token[a_location+num_a:]:
                                if ss_dir == "BA":
                                    self.syscon_dict["DEVICEPULL"][ss_token[1]][ss_b] = ss_a
                                elif ss_dir == "ABBA":
                                    self.syscon_dict["DEVICEPULL"][ss_token[1]][ss_a] = ss_b
                                    self.syscon_dict["DEVICEPULL"][ss_token[1]][ss_b] = ss_a
                                else:
                                    self.syscon_dict["DEVICEPULL"][ss_token[1]][ss_a] = ss_b
                        ss_dir = ss_token[2]
                        if ss_token[1] not in self.syscon_dict["DEVICEPULL"]:
                            # If device didn't exist, create it
                            self.syscon_dict["DEVICEPULL"][ss_token[1]] = { }

                        for ss_b in ss_token[4:]:
                            if ss_dir == "BA":
                                self.syscon_dict["DEVICEPULL"][ss_token[1]][ss_b] = ss_token[3]
                            elif ss_dir == "ABBA":
                                self.syscon_dict["DEVICEPULL"][ss_token[1]][ss_token[3]] = ss_b
                                self.syscon_dict["DEVICEPULL"][ss_token[1]][ss_b] = ss_token[3]
                            else:
                                self.syscon_dict["DEVICEPULL"][ss_token[1]][ss_token[3]] = ss_b

                    elif ss_token[0] == "DEVICEVOLT" and len( ss_token ) > 2:
                        # DEVICEVOLT, TYPE, VOLT, PIN [, PIN [, ... ]]
                        if ss_token[1] not in self.syscon_dict["DEVICEVOLT"]:
                            # If device didn't exist, create it
                            self.syscon_dict["DEVICEVOLT"][ss_token[1]] = { }
                        try:
                            device_volt = float( ss_token[2] )
                            for ss_pin in ss_token[3:]:
                                # If pin voltages specified, note them
                                self.syscon_dict["DEVICEVOLT"][ss_token[1]][ss_pin] = device_volt
                        except:
                            print "DEVICEVOLT: Unable to convert %s into voltage (%s)" % ( ss_token[2], ss )
                            pass

                    elif ss_token[0] == "DEVICEPIN" and len( ss_token ) > 5:
                        # DEVICEPIN, TYPE [, RC, ROWS, COLS, DIR]
                        # DEVICEPIN, TYPE [, ARB, ROW, COL, PIN]
                        # DEVICEPIN, TYPE, CATEGORY, NAME, PIN1, PIN2, ...
                        if ss_token[1] not in self.syscon_dict["DEVICEPIN"]:
                            # If device didn't exist, create it
                            self.syscon_dict["DEVICEPIN"][ss_token[1]] = {}
                            self.syscon_dict["DEVICEPIN"][ss_token[1]]["Rows"] = 0
                            self.syscon_dict["DEVICEPIN"][ss_token[1]]["Cols"] = 0
                            self.syscon_dict["DEVICEPIN"][ss_token[1]]["Map"] = {}
                            self.syscon_dict["DEVICEPIN"][ss_token[1]]["Category"] = {}

                        pin_type = ss_token[2].strip()
                        if pin_type == "RC":
                            try:
                                pin_rows = int( ss_token[3] )
                                pin_cols = int( ss_token[4] )
                            except:
                                pin_rows = 0
                                pin_cols = 0
                            pins = pin_rows * pin_cols
                            pin_dir = ss_token[5]
                            if pin_dir[0] == "T":
                                pin_row = 1
                            else:
                                pin_row = pin_rows
                            if pin_dir[1] == "L":
                                pin_col = 1
                            else:
                                pin_col = pin_cols

                            self.syscon_dict["DEVICEPIN"][ss_token[1]]["Rows"] = pin_rows
                            self.syscon_dict["DEVICEPIN"][ss_token[1]]["Cols"] = pin_cols

                            for pin_num in range( 1, pins+1 ):
                                self.syscon_dict["DEVICEPIN"][ss_token[1]]["Map"]["%d-%d" % ( pin_row, pin_col )] = "%d" % pin_num
                                # Increment row and column as appropriate
                                if pin_dir[2] == "H":
                                    if pin_dir[1] == "L":
                                        pin_col += 1            # Go right if we started at left
                                    else:
                                        pin_col -= 1            # Go left if we started at right
                                    # If we rolled over end of column, adjust row
                                    if pin_col < 1 or pin_col > pin_cols:
                                        if pin_dir[0] == "T":
                                            pin_row += 1        # Go down if we started at top
                                        else:
                                            pin_row -= 1        # Go up if we started at bottom
                                        if pin_col < 1:
                                            pin_col += pin_cols
                                        else:
                                            pin_col -= pin_cols
                                else:
                                    if pin_dir[0] == "T":
                                        pin_row += 1
                                    else:
                                        pin_row -= 1
                                    # If we rolled over end of row, adjust column
                                    if pin_row < 1 or pin_row > pin_rows:
                                        if pin_dir[1] == "L":
                                            pin_col += 1
                                        else:
                                            pin_col -= 1
                                        if pin_row < 1:
                                            pin_row += pin_rows
                                        else:
                                            pin_row -= pin_rows

                        elif pin_type == "ARB":
                            try:
                                pin_row = int( ss_token[3] )
                                pin_col = int( ss_token[4] )
                            except:
                                pin_row = 0
                                pin_col = 0

                            if pin_row > self.syscon_dict["DEVICEPIN"][ss_token[1]]["Rows"]:
                                self.syscon_dict["DEVICEPIN"][ss_token[1]]["Rows"] = pin_row
                            if pin_col > self.syscon_dict["DEVICEPIN"][ss_token[1]]["Cols"]:
                                self.syscon_dict["DEVICEPIN"][ss_token[1]]["Cols"] = pin_col
                            self.syscon_dict["DEVICEPIN"][ss_token[1]]["Map"]["%d-%d" % ( pin_row, pin_col )] = ss_token[5]

                        elif pin_type == "CATEGORY":
                            category_name = ss_token[3]
                            self.syscon_dict["DEVICEPIN"][ss_token[1]]["Category"][category_name] = []
                            for pin in ss_token[4:]:
                                self.syscon_dict["DEVICEPIN"][ss_token[1]]["Category"][category_name].append(pin)

                    elif ss_token[0] == "REFVOLT" and len( ss_token ) > 4:
                        ## REFVOLT, ID, REF, PIN, VOLT
                        # REFVOLT, ID, REF, VOLT, PIN [, PIN [, ... ]]
                        try:
                            ref_volt = float( ss_token[3] )

                            for ss_pin in ss_token[4:]:
                                id_ref_pin = "%s.%s.%s" % ( ss_token[1], ss_token[2], ss_pin )
                                if id_ref_pin not in self.syscon_dict["REFVOLT"]:
                                    # If device didn't exist, create it
                                    self.syscon_dict["REFVOLT"][id_ref_pin] = ref_volt
                                else:
                                    print "REFVOLT: Duplicate voltage specified."
                        except:
                            print "REFVOLT: Cannot convert %s into voltage (%s)" % ( ss_token[3], ss )
                            pass

                    else:
                        if not ss_processed:
                            print "Unable to process: %s" % ss

                s = f.readline()

            f.close()

        except Exception, e:
            print e
            pass

        return ( self.syscon_dict )


    def id_ref_pin_to_signal( self, id_ref_pin ):
        id_signal = ""
        token = id_ref_pin.split( '.' )
        if len( token ) > 2:
            id = token[0]
            ref = token[1]
            pin = token[2]

            ref_pin = "%s.%s" % ( ref, pin )

            if id in self.syscon_dict["NETLIST"]:
                if ref_pin in self.syscon_dict["NETLIST"][id]["REF.PIN"]:
                    signal = self.syscon_dict["NETLIST"][id]["REF.PIN"][ref_pin]

                    id_signal = "%s.%s" % ( id, signal )

        return id_signal


    def id_signal_to_id_ref_pin( self, id_signal ):
        id_ref_pin = ""
        token = id_signal.split( '.' )
        if len( token ) > 1:
            id = token[0]
            signal = token[1]

            if id in self.syscon_dict["NETLIST"]:
                if signal in self.syscon_dict["NETLIST"][id]["CONNECTION"]:
                    id_ref_pin = "%s.%s" % ( id, self.syscon_dict["NETLIST"][id]["CONNECTION"][signal][0] )

        return id_ref_pin


    def param_to_signal( self, param ):
        signal = ""
        param_type = "UNKNOWN"
        param_token = param.split( '.' )
        if len( param_token ) == 2:
            # One period means form is id.signal
            signal = param
            param_type = "ID_SIGNAL"
        elif len( param_token ) == 3:
            # Two periods means form is id.ref.pin
            signal = self.id_ref_pin_to_signal( param )
            print "Translating %s to %s" % ( param, signal )
            id_ref_pin = param
            param_type = "ID_REF_PIN"

        return ( param_type, signal )


    def check_trace( self, trace_from, trace_to, info_dict={} ):
        """
        check_trace( trace_from, trace_to, path )

        Determine trace between trace_from and trace_to if possible

        trace_from may be id_signal or id_ref_pin
        trace_to may be id_signal or id_ref_pin

        info_dict is dictionary as follows:
            ["PATH"] = [ ID.Ref, ... ]
            ["PULL"] = [ "ID.Type to Signal", ... ]
            ["PULL_ID_SIGNAL"] = [ "Signal", ... ]
            ["VOLT"] = [ Voltage, ... ]
        """

        ##print "check_trace( %s, %s )" % ( trace_from, trace_to )

        if "PATH" not in info_dict:
            info_dict["PATH"] = []
        if "PULL" not in info_dict:
            info_dict["PULL"] = []
        if "PULL_ID_SIGNAL" not in info_dict:
            info_dict["PULL_ID_SIGNAL"] = []
        if "VOLT" not in info_dict:
            info_dict["VOLT"] = []


        ( from_type, from_id_signal ) = self.param_to_signal( trace_from )
        ( to_type, to_id_signal ) = self.param_to_signal( trace_to )

        ( trace_flag, info_dict ) = self.trace_netlist_signal( from_id_signal, to_id_signal, info_dict )

        if trace_flag:
            # If path has no nodes, add a node if id.ref.pin was specified
            if len( info_dict["PATH"] ) == 0:
                if from_type == "ID_REF_PIN":
                    info_dict["PATH"].append( trace_from )
                elif to_type == "ID_REF_PIN":
                    info_dict["PATH"].append( trace_to )

        info_dict["TRACE"] = trace_flag

        return ( trace_flag, info_dict )


    def check_pull( self, pull_from, info_dict={} ):
        """
        check_pull( from_desired, to_desired, path )

        Determine pull-up/down on pull_from signal

        pull_from may be id_signal or id_ref_pin

        info_dict is dictionary as follows:
            ["PATH"] = [ ID.Ref, ... ]
            ["PULL"] = [ "ID.Type to Signal", ... ]
            ["PULL_ID_SIGNAL"] = [ "Signal", ... ]
            ["VOLT"] = [ Voltage, ... ]
        """

        print "check_pull( %s, %s )" % ( pull_from, info_dict )

        if "PATH" not in info_dict:
            info_dict["PATH"] = []
        if "PULL" not in info_dict:
            info_dict["PULL"] = []
        if "PULL_ID_SIGNAL" not in info_dict:
            info_dict["PULL_ID_SIGNAL"] = []
        if "VOLT" not in info_dict:
            info_dict["VOLT"] = []

        ( from_type, from_id_signal ) = self.param_to_signal( pull_from )

        # Add a node if id.ref.pin was specified
        if len( info_dict["PATH"] ) == 0:
            print "Decoding pull_from %s into %s (%s)" % ( pull_from, from_id_signal, from_type )
            if from_type == "ID_REF_PIN":
                info_dict["PATH"].append( from_id_signal )
            elif from_type == "ID_SIGNAL":
                id_ref_pin = self.id_signal_to_id_ref_pin( pull_from )
                print "Decoding ID_SIGNAL into %s" % id_ref_pin
                if len( id_ref_pin ) > 0:
                    info_dict["PATH"].append( id_ref_pin )

        ( info_dict ) = self.add_pulls( info_dict )

        return ( info_dict )


    def add_pulls( self, info_dict ):
        """
        add_pulls

        Add pull-up / pull-down information for path
        """

        print "\nadd_pulls( %s )" % info_dict
        ##print info_dict
        print "\n",

        path = info_dict["PATH"]

        id = ""
        ref = ""
        pin = ""
        checked_netnames = []
        for id_ref_pin in path:
            token = id_ref_pin.split( '.' )
            if len( token ) > 2:
                [ id, ref, pin ] = token[0:3]

            if id in self.syscon_dict["NETLIST"]:
                ref_pin = "%s.%s" % ( ref, pin )
                ##print "Extracting %s into %s, %s, %s; ref.pin = %s" % ( id_ref_pin, id, ref, pin, ref_pin )
                signal = self.syscon_dict["NETLIST"][id]["REF.PIN"][ref_pin]
                self.pull_netlist_signal( id, signal, info_dict, [] )

        return info_dict


    def pull_netlist_signal( self, id, signal, info_dict, pull_path ):
        """
        pull_netlist_signal( id, signal, info_dict ):

        Check all connections to a signal to see if they are resistors to a rail
        Follow straight-through devices if needed
        """

        print "\npull_netlist_signal( %s, %s, %s, %s )" % ( id, signal, info_dict, pull_path )
        ##print info_dict
        ##print pull_path
        ignore = False
        id_signal = "%s.%s" % (id, signal)
        rail = signal in self.syscon_dict["NETLIST"][id]["RAIL"]

        # if a signal is ignored, all the signals that trace to this ignored signal should also be added to ignored list.
        # This is not done during tracing because the tracing algorithm does not traverse all paths available to it. It only traverses
        # until the desired path is met
        if id_signal in self.syscon_dict["IGNORE"]["SIGNAL"]:
            ignore = True
            for temp_id_signal in info_dict["PULL_ID_SIGNAL"]:
                if temp_id_signal not in self.syscon_dict["IGNORE"]["SIGNAL"]:
                    self.syscon_dict["IGNORE"]["SIGNAL"].append(temp_id_signal)
        elif signal[0:2] != "NC" and id_signal not in info_dict["PULL_ID_SIGNAL"] or rail:
            if rail:
                print "%s is rail" % signal
                if len( pull_path ) > 1:
                    id_ref_pin = pull_path[-2]
                    [ id, ref, pin ] = id_ref_pin.split( '.' )
                    pull_part = self.syscon_dict["NETLIST"][id]["PART"][ref]
                    pull_info = "%s.%s (%s.%s) to %s" % ( id, pull_part, ref, pin, signal )
                else:
                    pull_info = "direct to %s" % signal
                info_dict["PULL"].append( pull_info )
                info_dict["VOLT"].append( self.syscon_dict["NETLIST"][id]["RAIL"][signal] )

            else:
                info_dict["PULL_ID_SIGNAL"].append(id_signal)
                test_id = ""
                test_signal = ""
                for ref_pin in self.syscon_dict["NETLIST"][id]["CONNECTION"][signal]:

                    if ignore == True:
                        break

                    [ ref, pin ] = ref_pin.split( '.' )
                    id_ref_pin = "%s.%s" % ( id, ref_pin )

                    # See if ref has specified voltage
                    if id_ref_pin in self.syscon_dict["REFVOLT"]:
                        pull_volt = self.syscon_dict["REFVOLT"][id_ref_pin]
                        pull_info = "%s specified at %.2f" % ( id_ref_pin, pull_volt )
                        print "Device %s specifies %s is %.2f" % ( ref, signal, pull_volt )
                        info_dict["PULL"].append( pull_info )
                        info_dict["VOLT"].append( pull_volt )

                    # See if ref is resistor and not dnp resistor or a capacitor and not dnp capacitor and not ignored
                    if ref not in self.syscon_dict["IGNORE"]["DEVICE"] and ref[0] == "R" and ref[1].isdigit() and ref in self.syscon_dict["NETLIST"][id]["PART"] and \
                       self.syscon_dict["NETLIST"][id]["PART"][ref].lower().find("dnp") == -1:
                        if pin == "1":
                            pull_pin = "2"
                        else:
                            pull_pin = "1"

                        pull_ref_pin = "%s.%s" % ( ref, pull_pin )
                        # See if opposite pin of resistor exists
                        if pull_ref_pin in self.syscon_dict["NETLIST"][id]["REF.PIN"]:
                            pull_signal = self.syscon_dict["NETLIST"][id]["REF.PIN"][pull_ref_pin]
                            # See if resistor is connected to a rail but ignore pull downs to GND as they cause unnecessary voltage conflicts
                            # If resistor not connected to rail, continue checking in case it is series resistor
                            rail = pull_signal in self.syscon_dict["NETLIST"][id]["RAIL"]
                            if not rail:
                                ( info_dict, ignore ) = self.pull_netlist_signal( id, pull_signal, info_dict, pull_path )
                            elif rail and not self.syscon_dict["NETLIST"][id]["RAIL"][pull_signal] == 0.0:
                                pull_part = self.syscon_dict["NETLIST"][id]["PART"][ref]
                                pull_info = "%s.%s (%s) to %s" % ( id, pull_part, pull_ref_pin, pull_signal )
                                info_dict["PULL"].append( pull_info )
                                info_dict["VOLT"].append( self.syscon_dict["NETLIST"][id]["RAIL"][pull_signal] )
                                print "Resistor %s (%s) connects %s to rail %s" % ( pull_ref_pin, pull_part, signal, pull_signal )

                    # See if signal goes through device
                    ref_type = self.syscon_dict["NETLIST"][id]["PART"][ref]
                    path_id = "%s.%s" % ( id, ref_pin )
                    # Don't follow a path we've been down before
                    if ref_type not in self.syscon_dict["IGNORE"]["DEVICE"] and ref_type in self.syscon_dict["DEVICE"] and path_id not in pull_path:
                        pull_path.append( path_id )
                        # Check if device pin has fixed voltage expectation
                        if ref_type in self.syscon_dict["DEVICEVOLT"]:
                            if pin in self.syscon_dict["DEVICEVOLT"][ref_type]:
                                pull_volt = self.syscon_dict["DEVICEVOLT"][ref_type][pin]
                                pull_info = "%s.%s (%s) to %.2f" % ( id, ref_pin, ref_type, pull_volt )
                                print "Device %s (%s) connects %s to %.2f" % ( ref, ref_type, signal, pull_volt )
                                info_dict["PULL"].append( pull_info )
                                info_dict["VOLT"].append( pull_volt )
                        ##print "Tracing device:", pull_path
                        ( id_signal, dummy ) = self.trace_device( id, ref_pin, ref_type, { "PATH": pull_path } )
                        if len( id_signal ) > 0:
                            [ test_id, test_signal ] = id_signal.split( '.' )
                            ##print "Looking for path from %s to %s" % ( id_signal, to_id_signal )
                            ( info_dict, ignore ) = self.pull_netlist_signal( test_id, test_signal, info_dict, pull_path )

                    # See if signal goes through device voltage linked pin
                    # Don't follow a path we've been down before
                    if ref_type not in self.syscon_dict["IGNORE"]["DEVICE"] and ref_type in self.syscon_dict["DEVICEPULL"] and path_id not in pull_path:
                        pull_path.append( path_id )
                        # Check if device pin has fixed voltage expectation
                        if ref_type in self.syscon_dict["DEVICEVOLT"]:
                            if pin in self.syscon_dict["DEVICEVOLT"][ref_type]:
                                pull_volt = self.syscon_dict["DEVICEVOLT"][ref_type][pin]
                                pull_info = "%s.%s (%s) to %.2f" % ( id, ref_pin, ref_type, pull_volt )
                                print "Device %s (%s) connects %s to %.2f" % ( ref, ref_type, signal, pull_volt )
                                info_dict["PULL"].append( pull_info )
                                info_dict["VOLT"].append( pull_volt )
                        ##print "Tracing device:", pull_path
                        ( id_signal, dummy ) = self.trace_device( id, ref_pin, ref_type, { "PATH": pull_path }, device_key="DEVICEPULL" )
                        if len( id_signal ) > 0:
                            [ test_id, test_signal ] = id_signal.split( '.' )
                            ##print "Looking for path from %s to %s" % ( id_signal, to_id_signal )
                            ( info_dict, ignore ) = self.pull_netlist_signal( test_id, test_signal, info_dict, pull_path )

                    # See if signal is attached to connection to harness
                    if id in self.syscon_dict["CONNECTION_REFS"]:
                        if ref in self.syscon_dict["CONNECTION_REFS"][id] and path_id not in pull_path:
                                pull_path.append(path_id)
                                test_info_dict = copy.copy( info_dict )
                                test_info_dict["PATH"] = pull_path  # trace connection function will continue adding to pull_path
                                ( id_signal, test_info_dict ) = self.trace_connection( id, ref_pin, test_info_dict )
                                if len( id_signal ) > 0:
                                    pull_path = test_info_dict["PATH"]
                                    [ test_id, test_signal ] = id_signal.split( '.' )
                                    ( info_dict, ignore ) = self.pull_netlist_signal( test_id, test_signal, info_dict, pull_path )

        if ignore == True:
            info_dict["PULL"] = []
            info_dict["VOLT"] = []

        return ( info_dict, ignore )


    def trace_netlist_signal( self, from_id_signal, to_id_signal, info_dict ):
        """
        trace_netlist_signal

        Locate all MAPs attached to a netlist signal and call
            trace_connection to see if they connect to the destination signal
        """

        ##print "trace_netlist_signal( %s, %s )" % ( from_id_signal, to_id_signal )
        ##print info_dict

        trace_success = False
        from_token = from_id_signal.split( '.' )
        to_token = to_id_signal.split( '.' )
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

        if valid_params and from_id_signal == to_id_signal:
            ##print "\n***\n\n*** SUCCESS\n\n"
            trace_success = True
        # do not attempt to trace GND signals since this function is only called on ID.signal_name. If the CHECKTRACE specified in input
        # .csv file was true, the from_signal would == to_signal and the first condition would be met. Otherwise, we end up traversing
        # thousands of ground connections.
        elif valid_params and from_signal != "GND" and to_signal != "GND":
            trace_success = False
            if from_id in self.syscon_dict["NETLIST"]:
                if from_signal in self.syscon_dict["NETLIST"][from_id]["CONNECTION"]:
                    for ref_pin in self.syscon_dict["NETLIST"][from_id]["CONNECTION"][from_signal]:
                        ref_token = ref_pin.split( '.' )
                        ref = ref_token[0]
                        pin = ref_token[1]
                        traced = False

                        # See if signal is attached to connection to harness
                        if from_id in self.syscon_dict["CONNECTION_REFS"] and not trace_success:
                            if ref in self.syscon_dict["CONNECTION_REFS"][from_id]:
                                traced = True
                                path_id = "%s.%s" % ( from_id, ref_pin )
                                # Don't follow a path we've been down before
                                if path_id not in info_dict["PATH"]:
                                    test_path = copy.copy( info_dict["PATH"] )
                                    test_path.append( path_id )
                                    test_info_dict = copy.copy( info_dict )
                                    test_info_dict["PATH"] = test_path

                                    ( id_signal, test_info_dict ) = self.trace_connection( from_id, ref_pin, test_info_dict )
                                    if len( id_signal ) > 0:
                                        ##print "Looking for path from %s to %s" % ( id_signal, to_id_signal )
                                       ( trace_success, test_info_dict ) = self.trace_netlist_signal( id_signal, to_id_signal, test_info_dict )



                        # If signal not attached to connection to harness,
                        # see if signal goes through device
                        if not traced:
                            ref_type = self.syscon_dict["NETLIST"][from_id]["PART"][ref]
                            path_id = "%s.%s" % ( from_id, ref_pin )
                            # Don't follow a path we've been down before
                            if ref_type in self.syscon_dict["DEVICE"] and ref_type not in self.syscon_dict["IGNORE"]["DEVICE"] and path_id not in info_dict["PATH"]:
                                traced = True
                                test_path = copy.copy( info_dict["PATH"] )
                                test_path.append( path_id )
                                test_info_dict = copy.copy( info_dict )
                                test_info_dict["PATH"] = test_path
                                ( id_signal, test_info_dict ) = self.trace_device( from_id, ref_pin, ref_type, test_info_dict )
                                if len( id_signal ) > 0:
                                    ##print "Looking for path from %s to %s" % ( id_signal, to_id_signal )
                                    ( trace_success, test_info_dict ) = self.trace_netlist_signal( id_signal, to_id_signal, test_info_dict )

                        if trace_success:
                            info_dict = test_info_dict
                            break

        return ( trace_success, info_dict )


    def trace_connection( self, from_id, from_ref_pin, info_dict ):
        """
        Returns id_signal at end of connection

        Will trace through harnesses until it gets to a signal name in a netlist
        """

        print "trace_connection( %s.%s )" % ( from_id, from_ref_pin )
        print info_dict

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
            if from_id_ref in self.syscon_dict["CONNECTION"]:
                to_id_ref = self.syscon_dict["CONNECTION"][from_id_ref]
                to_token = to_id_ref.split( '.' )
                if len( to_token ) > 1:
                    to_id = to_token[0]
                    to_ref = to_token[1]
                # Pins are always the same on either side of a connection
                to_ref_pin = "%s.%s" % ( to_ref, from_pin )

                ##print "%s connected to %s" % ( from_id_ref, to_id_ref )

                # Check to see if connection is to harness
                if to_id in self.syscon_dict["HARNESS"]:
                    ##print "%s is a harness, looking for %s" % ( to_id, to_ref_pin )
                    ##print self.syscon_dict["HARNESS"][to_id]
                    if to_ref_pin in self.syscon_dict["HARNESS"][to_id]:
                        connected_ref_pin = self.syscon_dict["HARNESS"][to_id][to_ref_pin]
                        info_dict["PATH"].append( "%s.%s" % ( to_id, to_ref_pin ) )
                        info_dict["PATH"].append( "%s.%s" % ( to_id, connected_ref_pin ) )

                        ##print "%s is connected to %s" % ( to_id_ref, connected_ref_pin )
                        ( to_id_signal, info_dict ) = self.trace_connection( to_id, connected_ref_pin, info_dict )

                # Otherwise connection should be to netlist
                elif to_id in self.syscon_dict["NETLIST"]:
                    ##print "%s is a PCB, looking for %s" % ( to_id, to_ref_pin )
                    ##print self.syscon_dict["NETLIST"][to_id]
                    if to_ref_pin in self.syscon_dict["NETLIST"][to_id]["REF.PIN"]:
                        info_dict["PATH"].append( "%s.%s" % ( to_id, to_ref_pin ) )
                        to_signal = self.syscon_dict["NETLIST"][to_id]["REF.PIN"][to_ref_pin]
                        to_id_signal = "%s.%s" % ( to_id, to_signal )
                        ##print "%s connected to %s" % ( to_ref_pin, to_id_signal )

        return ( to_id_signal, info_dict )


    def trace_device( self, from_id, from_ref_pin, from_ref_type, info_dict=None, device_key="DEVICE" ):
        """
        Returns an array of id_signal at end of device

        Will trace through device
        """

        print "trace_device( %s.%s, %s )" % ( from_id, from_ref_pin, from_ref_type )
        ##print info_dict

        valid_params = True
        device_traced = False
        to_id_signal = []

        from_token = from_ref_pin.split( '.' )
        if len( from_token ) > 1:
            from_ref = from_token[0]
            from_pin = from_token[1]
        else:
            valid_params = False

        ##print "Checking %s pin %s" % ( from_ref, from_pin )

        if valid_params:
            if from_pin in self.syscon_dict[device_key][from_ref_type]:
                to_pin = self.syscon_dict[device_key][from_ref_type][from_pin]
                to_ref_pin = "%s.%s" % ( from_ref, to_pin )
                path_info = "%s.%s" % ( from_id, to_ref_pin )

                ##print "%s connected to %s" % ( from_ref_pin, to_ref_pin )

                if from_id in self.syscon_dict["NETLIST"]:
                    if to_ref_pin in self.syscon_dict["NETLIST"][from_id]["REF.PIN"]:
                        if info_dict is None:
                            device_traced = True
                        else:
                            if path_info not in info_dict["PATH"]:
                                ##print "Device traced:",info_dict
                                info_dict["PATH"].append( path_info )
                                ##print "New path:",info_dict
                                device_traced = True
                        if device_traced:
                            to_signal = self.syscon_dict["NETLIST"][from_id]["REF.PIN"][to_ref_pin]
                            to_id_signal = "%s.%s" % ( from_id, to_signal )
                            ##print "%s connected to %s" % ( to_ref_pin, to_id_signal )

        return ( to_id_signal, info_dict )


    def write_check_trace( self, f ):
        """
        Writes trace of desired signals:
            COMMENT,DESIRE FROM,DESIRE TO,DESIRE VOLTAGE,TRACE FLAG,VOLT FLAG,COMMON VOLT FLAG,COMMON VOLTAGE,PATH,PULL,VOLT
        """
        print "write_check_trace()"
        info_dict = {}
        for ( from_signal, to_signal, check_dict ) in self.syscon_dict["CHECKTRACE"]:
            if from_signal[0:6] == "$$##__":
                info = "\n%s" % self.syscon_dict["COMMENTS"][from_signal]
            else:
                print "\nChecking %s -> %s\n" % ( from_signal, to_signal )
                ( trace_flag, info_dict ) = self.check_trace( from_signal, to_signal, {} )

                if "VOLT" in check_dict or trace_flag:
                    ( info_dict ) = self.add_pulls( info_dict )

                info = self.gen_check_line( from_signal, to_signal, check_dict, info_dict )
            f.write( "%s\n" % info )


    def write_check_volt( self, f ):
        """
        Writes trace of desired signals:
            COMMENT,DESIRE FROM,DESIRE TO,DESIRE VOLTAGE,TRACE FLAG, IGNORE FLAG, VOLT FLAG,COMMON VOLT FLAG,COMMON VOLTAGE,PATH,PULL,VOLT
        """

        print "write_check_volt()"

        for ( signal, check_dict ) in self.syscon_dict["CHECKVOLT"]:
            if signal[0:6] == "$$##__":
                info = "\n%s" % self.syscon_dict["COMMENTS"][signal]
            else:
                print "\nChecking voltage on %s\n" % ( signal )
                ( info_dict ) = self.check_pull( signal, {} )

                info = self.gen_check_line( signal, signal, check_dict, info_dict )
            f.write( "%s\n" % info )


    def write_all_volt(self, f):
        """
        Writes trace of desired signals, used to see all voltage pulls on every net.
            COMMENT,DESIRE FROM,DESIRE TO,DESIRE VOLTAGE,TRACE FLAG, IGNORE FLAG, VOLT FLAG,COMMON VOLT FLAG,COMMON VOLTAGE,PATH,PULL,VOLT

        First, the conflicting voltage signals from each board are written
        Then, the signals which have no voltage information (so it can be easier investigated what is missing which resulted in no voltage info)
        Lastly, the non-conflicting voltage signals are written
        """
        info = ""
        check_dict = {}
        signal_dict = { "CONFLICT": {}, "NA": {}, "NON-CONFLICT": {} } # { "CONFLICT": { Board_ID:[(Signal, Info Dict),...], ... }, ... }


        for id in self.syscon_dict["NETLIST_FILE"]:
            signal_dict["CONFLICT"][id] = []
            signal_dict["NA"][id] = []
            signal_dict["NON-CONFLICT"][id] = []

            f.write( "\n\n,%s CONFLICT SIGNALS\n\n" % id)
            for signal in self.syscon_dict["NETLIST"][id]["CONNECTION"]:
                id_signal = "%s.%s" % (id, signal)
                ( info_dict ) = self.check_pull(id_signal, {} )

                common_volt_flag = True
                if len( info_dict["VOLT"] ) > 0:
                    # Check for common pull-up/down voltage
                    common_volt = info_dict["VOLT"][0]
                    for volt in info_dict["VOLT"]:
                        if volt != common_volt:
                            common_volt_flag = False
                            break

                    if common_volt_flag:
                        signal_dict["NON-CONFLICT"][id].append( (id_signal, info_dict) )
                    else:
                        signal_dict["CONFLICT"][id].append( (id_signal, info_dict) )
                        info = self.gen_check_line( id_signal, id_signal, check_dict, info_dict )
                        f.write( "%s\n" % info )
                else:
                    signal_dict["NA"][id].append( (id_signal, info_dict) )

        # Write the NA Signals
        for id in self.syscon_dict["NETLIST_FILE"]:
            f.write( "\n\n,%s NO VOLTAGE SIGNALS\n\n" % id)
            for (id_signal, info_dict) in signal_dict["NA"][id]:
                info = self.gen_check_line( id_signal, id_signal, check_dict, info_dict )
                f.write( "%s\n" % info )

        # Write the remaining non-conflicting signals
        for id in self.syscon_dict["NETLIST_FILE"]:
            f.write( "\n\n,%s NON-CONFLICTING SIGNALS\n\n" % id)
            for (id_signal, info_dict) in signal_dict["NON-CONFLICT"][id]:
                info = self.gen_check_line( id_signal, id_signal, check_dict, info_dict )
                f.write( "%s\n" % info )

    def gen_check_line( self, from_id_signal, to_id_signal, check_dict, info_dict ):
        """
        Writes trace of desired signals:
            COMMENT,DESIRE FROM,DESIRE TO,DESIRE VOLTAGE,TRACE FLAG,IGNORE FLAG,VOLT FLAG,COMMON VOLT FLAG,COMMON VOLTAGE,PATH,PULL,VOLT
        """
        from_token = from_id_signal.split( "." )
        to_token = to_id_signal.split( "." )
        from_signal = from_token[1]
        to_signal = to_token[1]

        info = ',="%s",="%s",' % ( from_id_signal, to_id_signal )
        if "VOLT" in check_dict:
            desired_volt = check_dict["VOLT"]
            info += '="%.2f",' % desired_volt
        else:
            info += ','

        trace_flag = False
        if "TRACE" in info_dict:
            trace_flag = info_dict["TRACE"]
            if trace_flag:
                info += "TRUE,"
            else:
                info += "FALSE,"
        else:
            info += "#N/A,"

        # Ignore signal for voltage/trace flag
        if from_id_signal in self.syscon_dict["IGNORE"]["SIGNAL"] or to_id_signal in self.syscon_dict["IGNORE"]["SIGNAL"]:
            info += "TRUE,"
        else:
            info += "FALSE,"

        common_volt_flag = False
        if len( info_dict["VOLT"] ) > 0:
            # Check for common pull-up/down voltage
            common_volt = info_dict["VOLT"][0]
            common_volt_flag = True
            for volt in info_dict["VOLT"]:
                if volt != common_volt:
                    ##print "Voltage mismatch: %g vs %g" % ( volt, common_volt )
                    common_volt_flag = False

        if "VOLT" in check_dict:
            if common_volt_flag:
                # If we have both a desired voltage and a pull-up/down, check if they match
                if check_dict["VOLT"] == common_volt:
                    info += "TRUE,"
                else:
                    info += "FALSE,"
            else:
                # If we have a desired voltage but no (or mismatched) pull-up/down, then we have a problem
                info += "FALSE,"
        else:
            # If we don't have a desired voltage, there is no possible match
            info += "#N/A,"

        if len( info_dict["VOLT"] ) > 0:
            # If we found pull-up/down, write it and the common voltage
            if common_volt_flag:
                info += 'TRUE,="%.2f",' % common_volt
            else:
                info += 'FALSE,#N/A,'
        else:
            info += '#N/A,#N/A,'

        info += "PATH,"
        for id_ref_pin in info_dict["PATH"]:
            info += '="%s",' % id_ref_pin
        info += "PULL,"
        for pull in info_dict["PULL"]:
            info += '="%s",' % pull
        info += "VOLT,"
        for volt in info_dict["VOLT"]:
            info += '="%.2f",' % volt

        return info


    def gen_signal_relation ( self, signal_relation, device_type ):
        ( pin, int_signal, ext_signal, io_standard ) = signal_relation
        ret_string = "Location: %s, Signal: %s, IO_Standard: %s" % ( pin, ext_signal, io_standard )

        if device_type == "XILINX_FPGA":
            # Example:
            # NET "dad_addr[0]" IOSTANDARD = LVCMOS25;
            # NET "dad_addr[0]" LOC = AA34;
            ret_string = 'NET "%s" IOSTANDARD = %s;\nNET "%s" LOC = %s;' % ( ext_signal, io_standard, ext_signal, pin )
        elif device_type == "ALTERA_FPGA":
            # Example:
            # set_location_assignment PIN_AA1 -to FBB_CPU2FD_D[3]
            # set_instance_assignment -name IO_STANDARD "3.0-V LVTTL" -to FBB_CPU2FD_D[3]
            ret_string = "set_location_assignment PIN_%s -to %s\n" % ( pin, ext_signal )
            ret_string += 'set_instance_assignment -name IO_STANDARD "%s" -to %s' % ( io_standard, ext_signal )
        elif device_type == "LATTICE_CPLD":
            # Example:
            # LOCATE COMP "STEALTH_MODE" SITE "F11" ;
            # IOBUF PORT "STEALTH_MODE" IO_TYPE=LVCMOS33 ;
            ret_string = 'LOCATE COMP "%s" SITE "%s" ;\nIOBUF PORT "%s" IO_TYPE=%s ;' % (ext_signal, pin, ext_signal, io_standard)

        return ret_string

    def write_signal_relations ( self ):
        for id_ref in self.syscon_dict["REFSIG"]:
            ( id, ref ) = id_ref.split( '.' )
            if id in self.syscon_dict["NETLIST_FILE"] and ref in self.syscon_dict["NETLIST"][id]["PART"]:
                type = self.syscon_dict["NETLIST"][id]["PART"][ref]
                if type in self.syscon_dict["DEVICEPARAM"]:
                    if "DEVICETYPE" in self.syscon_dict["DEVICEPARAM"][type]:
                        device_type = self.syscon_dict["DEVICEPARAM"][type]["DEVICETYPE"]
                        out_filename = "%s_%s_%s.txt" % ( id, ref, device_type )
                        try:
                            f = open( out_filename, "w" )
                            print "Writing signal relations to %s" % out_filename
                            info = ""
                            for signal_relation in self.syscon_dict["REFSIG"][id_ref]:
                                info = self.gen_signal_relation ( signal_relation, device_type )
                                f.write ( "%s\n\n" % info)
                            f.close()
                        except:
                            pass


    def write_pin_signals( self, f ):
        for id_ref in self.syscon_dict["MAP_SEQ"]:
            if id_ref[0:6] == "$$##__":
                info = "\n%s" % self.syscon_dict["COMMENTS"][id_ref]
                f.write( "%s\n" % info )
            else:
                id_token = id_ref.split( '.' )
                id = id_token[0]
                ref = id_token[1]
                if ref in self.syscon_dict["NETLIST"][id]["PART"]:
                    con_type = self.syscon_dict["NETLIST"][id]["PART"][ref]
                else:
                    con_type = ""
                f.write( '\n="%s",="%s"\n="%s",="%s"\n' % ( id_ref, self.syscon_dict["MAP"][id_ref], id_ref, con_type ) )
                display_type = self.syscon_dict["DEVICEPIN"]

                # if no ordering specified, then just list them vertically
                if not con_type in self.syscon_dict["DEVICEPIN"]:
                    if ref in self.syscon_dict["NETLIST"][id]["PART"]:
                        for pin in self.syscon_dict["NETLIST"][id]["PINS"][ref]:
                            info = ",,"
                            ref_pin = "%s.%s" % (ref, pin)
                            net = ""
                            if ref_pin in self.syscon_dict["NETLIST"][id]["REF.PIN"]:
                                net = self.syscon_dict["NETLIST"][id]["REF.PIN"][ref_pin]
                            info += '="%s",="%s"\n' % (pin, net)
                            f.write( "%s" % info )
                else:
                    # For displaying device pinsouts:
                    if len(self.syscon_dict["DEVICEPIN"][con_type]["Category"]) > 0:
                        pins_on_device = self.syscon_dict["NETLIST"][id]["PINS"][ref]
                        pin_flags = dict( zip( pins_on_device, [0]*len(pins_on_device)) )

                        for category_name in self.syscon_dict["DEVICEPIN"][con_type]["Category"]:
                            new_category = True
                            info = ',="%s",' % category_name
                            for pin in self.syscon_dict["DEVICEPIN"][con_type]["Category"][category_name]:
                                pin_flags[pin] = 1
                                if not new_category:
                                    info = ",,"
                                new_category = False
                                ref_pin = "%s.%s" % (ref, pin)
                                net = ""
                                if ref_pin in self.syscon_dict["NETLIST"][id]["REF.PIN"]:
                                    net = self.syscon_dict["NETLIST"][id]["REF.PIN"][ref_pin]
                                info += '="%s",="%s"\n' % (pin, net)
                                f.write( "%s" % info )

                        new_category = True
                        info = ',="REMAINING PINS",'
                        for pin in pin_flags:
                            if pin_flags[pin] == 0:
                                if not new_category:
                                    info = ",,"
                                new_category = False
                                ref_pin = "%s.%s" % (ref, pin)
                                net = ""
                                if ref_pin in self.syscon_dict["NETLIST"][id]["REF.PIN"]:
                                    net = self.syscon_dict["NETLIST"][id]["REF.PIN"][ref_pin]
                                info += '="%s",="%s"\n' % (pin, net)
                                f.write( "%s" % info )

                    # connector pinout for the most part
                    else:
                        pin_rows = self.syscon_dict["DEVICEPIN"][con_type]["Rows"]
                        pin_cols = self.syscon_dict["DEVICEPIN"][con_type]["Cols"]
                        for pin_row in range( 1, pin_rows+1 ):
                            info = ",,"
                            for pin_col in range( 1, pin_cols+1 ):
                                row_col = "%d-%d" % ( pin_row, pin_col )
                                pin = ""
                                net = ""
                                if row_col in self.syscon_dict["DEVICEPIN"][con_type]["Map"]:
                                    pin = self.syscon_dict["DEVICEPIN"][con_type]["Map"][row_col]
                                    ref_pin = "%s.%s" % ( ref, pin )
                                    if ref_pin in self.syscon_dict["NETLIST"][id]["REF.PIN"]:
                                        net = self.syscon_dict["NETLIST"][id]["REF.PIN"][ref_pin]
                                info += '="%s",="%s",'% ( pin, net )
                            f.write( "%s\n" % info )


def usage():
    print """

system_connections.py [-opt]

    Option                      Description
    -h          --help          Display this help

    -f FILENAME --file=FILENAME Filename to process
    -o FILENAME --out=FILENAME  Filename for ouotput
                                Outputs FILENAME_check.csv
                                Outputs FILENAME_maps.csv
    -v VALUE    --volt=VALUE    Specifies if complete netlist voltage check is necessary
"""


def main( argv ):
    out_stem = ""

    try:
        opts, args = getopt.getopt( argv, "hf:o:v:",
                    ["help", "file=", "out=", "volt=" ] )

    except getopt.GetoptError, err:
        print str(err)
        usage()
        sys.exit(2)

    syscon = system_connections()
    system_volt_check = False

    for opt, arg in opts:
        if opt in ("-f", "--file"):
            filename = arg
            syscon.load_syscon_csv( arg )
        if opt in ("-o", "--out"):
            out_stem = arg
            print "Output filename stem = %s" % out_stem
        if opt in ("-v", "--volt"):
            try:
                num_val = int( arg )
            except:
                num_val = 0

            if num_val == 1:
                system_volt_check = True
        elif opt in ("-h", "--help"):
            usage()
            sys.exit()

##    filename = "main.csv"
##    syscon.load_syscon_csv( filename )
##    out_stem = "Main"

    keys = syscon.syscon_dict.keys()
    print keys
    keys.remove( "NETLIST" )
    keys.remove( "HARNESS" )
    keys.remove( "DEVICEPIN" )
    for key in keys:
        print "%s:" % key,
        print syscon.syscon_dict[key]

    if len( out_stem ) > 0:
        out_filename = "%s_check.csv" % out_stem
        try:
            f = open( out_filename, "w" )
            print "Writing checks to %s" % out_filename
            syscon.write_check_trace( f )
            syscon.write_check_volt( f )
            f.close()

            if system_volt_check:
                file = open ("Volt_check.csv", "w" )
                print "Writing volt checks to Volt_check.csv"
                syscon.write_all_volt( file )
                file.close()
        except:
            pass

        out_filename = "%s_map.csv" % out_stem
        try:
            f = open( out_filename, "w" )
            print "Writing maps to %s" % out_filename
            syscon.write_pin_signals( f )
            f.close()
        except:
            pass

        syscon.write_signal_relations()

def basic_main():

    print "SYSTEM_CONNECTIONS.py: System Connections Verification Class"

    syscon = system_connections( "check.csv" )
    keys = syscon.syscon_dict.keys()
    print keys
    keys.remove( "NETLIST" )
    keys.remove( "HARNESS" )
    keys.remove( "DEVICEPIN" )
    for key in keys:
        print "%s:" % key,
        print syscon.syscon_dict[key]

    for key in syscon.syscon_dict["NETLIST"]:
        print "%s:" % key,
        print syscon.syscon_dict["NETLIST"][key]["RAIL"]

    f = open( "syscon_desired.csv", "w" )
    syscon.write_check_trace( f )
    syscon.write_check_volt( f )
    f.close()
    f = open( "syscon_maps.csv", "w" )
    syscon.write_pin_signals( f )
    f.close()

    ##( test ) = load_syscon_csv( "syscon.csv" )
    ##print test["DEVICE"]



if __name__ == "__main__":
    main(sys.argv[1:])


# vi:set shiftwidth=4 tabstop=4:
# vim:set expandtab list lcs=tab\:>>:

