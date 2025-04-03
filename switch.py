#!/usr/bin/python3
import sys
import struct
import wrapper
import threading
import time
import os
import ctypes
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, get_interface_name

CAM_table = {}
BPDU_DEST_MAC = "01:80:c2:00:00:00"

class BPDU:
    def __init__(self, root_bridge_ID: int, sender_bridge_ID: int, root_path_cost: int):
        self.root_bridge_ID = root_bridge_ID
        self.sender_bridge_ID = sender_bridge_ID
        self.root_path_cost = root_path_cost

    def serialize_bpdu(self, switch_MAC_address):
        """
        Serializeaza un obiect de tip BPDU in bytes pentru a putea fi trimis mai departe
        """

        root_bridge_bytes = self.root_bridge_ID.to_bytes(4,'big')
        sender_bridge_bytes = self.sender_bridge_ID.to_bytes(4,'big')
        root_path_cost_bytes = self.root_path_cost.to_bytes(4,'big')

        data_length = 29
        data = ctypes.create_string_buffer(data_length)

        # ETHERNET
        bpdu_dest_mac_bytes = bytes.fromhex(BPDU_DEST_MAC.replace(":", ""))
        data[0:6] = bpdu_dest_mac_bytes
        data[6:12] = switch_MAC_address
        data[12] = 0x00
        data[13] = 0x03

        # LLC
        data[14] = 0x42
        data[15] = 0x42
        data[16] = 0x03

        #BPDU
        data[17:21] = sender_bridge_bytes
        data[21:25] = root_bridge_bytes
        data[25:29]= root_path_cost_bytes

        return data_length, bytes(data.raw)

class Switch:
    def __init__(self, priority_value: int, ports, MAC_address: bytes):
        self.priority_value = priority_value
        self.own_bridge_ID = priority_value
        self.root_bridge_ID = priority_value
        self.root_path_cost = 0

        self.ports = ports  
        # este dictionarul din switch_config, respectiv : {"id" : interface_id, "state" : None}

        self.root_port = None
        self.MAC_address = MAC_address

    
    def is_root(self):
            return self.own_bridge_ID == self.root_bridge_ID

    def get_port_state(self, given_port):
        for port in self.ports:
            if port["id"] == given_port:
                return port["state"]
            
    def set_port_state(self, given_port, state):
        for port in self.ports:
            if port["id"] == given_port:
                port["state"] = state

    def set_all_trunk_ports_to_state(self, state):
        for port in self.ports:
            port["state"] = state

    def send_bpdu(self):
        if self.is_root():
            # Send BPDU on all trunk ports
            bdpu = BPDU(self.own_bridge_ID, self.own_bridge_ID, 0)
            for port in self.ports:
                length, bpdu_frame = bdpu.serialize_bpdu(self.MAC_address)
            
                send_to_link(port["id"], length, bpdu_frame)

    def deserialize_bpdu(self, serialized_data):
        """
        Deserializeaza un frame bpdu primit in bytes si intoarce un obiect de tip BPDU
        """

        data_length = 29
        if len(serialized_data) != data_length:
            raise ValueError("Lungimea cadrului bpdu incorecta")

        # ETHERNET
        dest_mac = serialized_data[0:6]
        src_mac = serialized_data[6:12]
        ether_type1 = serialized_data[12]
        ether_type2 = serialized_data[13]

        # LLC - DSAP, SSAP, Control
        dsap = serialized_data[14]
        ssap = serialized_data[15]
        control = serialized_data[16]

        # BPDU
        sender_bridge_id = int.from_bytes(serialized_data[17:21], 'big')
        root_bridge_id = int.from_bytes(serialized_data[21:25], 'big')
        root_path_cost = int.from_bytes(serialized_data[25:29], 'big')

        bpdu = BPDU(root_bridge_id, sender_bridge_id, root_path_cost)
        return bpdu


    def receive_bpdu(self, bpdu : BPDU, incoming_port):

        we_were_root_bridge = self.is_root()

        if bpdu.root_bridge_ID < self.root_bridge_ID:
            self.root_bridge_ID = bpdu.root_bridge_ID
            self.root_path_cost = bpdu.root_path_cost + 10
            self.root_port = incoming_port

            if we_were_root_bridge:

                # set all interfaces not to hosts to blocking except the root port 
                for port in self.ports:
                    if port["id"] != self.root_port:
                        port["state"] = "BLOCKING"

            for port in self.ports:
                    if port["id"] == self.root_port and port["state"] == "BLOCKING":
                        port["state"] = "LISTENING"
            
            # Update BPDU
            new_bpdu = BPDU(self.root_bridge_ID, self.own_bridge_ID, self.root_path_cost)

            # Forward BPDU to all OTHER trunk ports
            for port in self.ports:
                if port["id"] != incoming_port:
                    length, bpdu_frame = new_bpdu.serialize_bpdu(self.MAC_address)
                    send_to_link(port["id"], length, bpdu_frame)

        elif bpdu.root_bridge_ID == self.root_bridge_ID:
            if incoming_port == self.root_port and bpdu.root_path_cost + 10 < self.root_path_cost:
                self.root_path_cost = bpdu.root_path_cost + 10

            elif incoming_port != self.root_port:
                if bpdu.root_path_cost > self.root_path_cost:
                    if self.get_port_state(incoming_port) == "BLOCKING":
                        self.set_port_state(incoming_port, "LISTENING")
        
        elif bpdu.sender_bridge_ID == self.own_bridge_ID:
            self.set_port_state(incoming_port, "BLOCKING")
        
        else:
            # Drop BPDU
            pass
        
        if self.own_bridge_ID == self.root_bridge_ID:
            self.set_all_trunk_ports_to_state("LISTENING")

    
    def send_to_trunk_port_unicast(self,switch_config, dest_interface, src_interface_type, length, data, interface):

        if self.get_port_state(dest_interface) == "BLOCKING":
            return -1

        if src_interface_type == "trunk":
            send_to_link(dest_interface, length, data)
        else:
            vlan_id = switch_config["interfaces"][get_interface_name(interface)]["vlan_id"]
            new_Q_frame = add_vlan_header(data, vlan_id)
            send_to_link(dest_interface, len(new_Q_frame), new_Q_frame)
        
        return 0 # Frame trimis cu succes
    
    def send_to_access_port_unicast(self,switch_config, dest_interface, src_interface_type, length, data, interface, vlan_id):
        if src_interface_type == "trunk":
            dest_interface_vlan = switch_config["interfaces"][get_interface_name(dest_interface)]["vlan_id"]

            if vlan_id != dest_interface_vlan:
                # Drop
                return -1

            cleaned_frame = remove_vlan_header(data)
            send_to_link(dest_interface, len(cleaned_frame), cleaned_frame)

        else:
            dest_interface_vlan = switch_config["interfaces"][get_interface_name(dest_interface)]["vlan_id"]
            src_interface_vlan = switch_config["interfaces"][get_interface_name(interface)]["vlan_id"]

            if src_interface_vlan != dest_interface_vlan:
                # Drop
                return -1

            send_to_link(dest_interface, length, data)

        return 0    # Frame trimis cu succes 

    def send_to_all_from_trunk_port(self, switch_config,interface, length, data, interfaces, vlan_id):

         for intf in interfaces:
                if intf != interface:
                    # trimit pe toate interfetele access din acelasi VLAN (fara header Q) si pe toate interfetele trunk (cu header Q)
                    intf_type = switch_config["interfaces"][get_interface_name(intf)]["type"]
                    if intf_type == "trunk": 
                        if self.get_port_state(intf) != "BLOCKING":
                            send_to_link(intf, length, data)
                    else:
                        if switch_config["interfaces"][get_interface_name(intf)]["vlan_id"] == vlan_id:
                            cleaned_frame = remove_vlan_header(data)
                            send_to_link(intf, len(cleaned_frame), cleaned_frame)

    def send_to_all_from_access_port(self,switch_config, interface, length, data, interfaces, vlan_id ):

        # Preluam VLAN ID-ul asociat portului de tip ACCESS de pe care a venit frame-ul
        vlan_id = switch_config["interfaces"][get_interface_name(interface)]["vlan_id"]

        for intf in interfaces:
            if intf != interface:
                if "vlan_id" in switch_config["interfaces"][get_interface_name(intf)]:
                    if switch_config["interfaces"][get_interface_name(intf)]["vlan_id"] == vlan_id:
                        send_to_link(intf, length, data)
                else:
                    if self.get_port_state(intf) == "BLOCKING":
                        continue
                    new_frame = add_vlan_header(data, vlan_id)
                    send_to_link(intf, len(new_frame), new_frame)

    def send_to_all(self,switch_config, interface, length, data, interfaces, vlan_id):
        """
        Face flooding in retea atunci cand nu are intrare in tabela CAM 
        sau face BROADCAST, atunci cand vrea sa trimita pe o destinatie de tip broadcast
        """
        src_interface_type = switch_config["interfaces"][get_interface_name(interface)]["type"]

        if src_interface_type == "trunk":
            self.send_to_all_from_trunk_port(switch_config, interface, length, data, interfaces, vlan_id)
        else:
            self.send_to_all_from_access_port(switch_config, interface, length, data, interfaces, vlan_id)

# Metode globale

def parse_ethernet_header(data):
    # Unpack the header fields from the byte array
    # dest_mac, src_mac, ethertype = struct.unpack('!6s6sH', data[:14])
    dest_mac = data[0:6]
    src_mac = data[6:12]
    
    # Extract ethertype. Under 802.1Q, this may be the bytes from the VLAN TAG
    ether_type = (data[12] << 8) + data[13]

    vlan_id = -1
    # Check for VLAN tag (0x8100 in network byte order is b'\x81\x00')
    if ether_type == 0x8200:
        vlan_tci = int.from_bytes(data[14:16], byteorder='big')
        vlan_id = vlan_tci & 0x0FFF  # extract the 12-bit VLAN ID
        ether_type = (data[16] << 8) + data[17]

    return dest_mac, src_mac, ether_type, vlan_id

def create_vlan_tag(vlan_id):
    return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

def send_bdpu_every_sec(switch: Switch):
    while True:
        switch.send_bpdu()
        time.sleep(1)

def parse_switch_config(SWITCH_ID, num_interfaces):
    """
    Parseaza fisierul de configuratie al switch-ului (switchX.cfg) in functie de id-ul X al switch-ului dat ca parametru
    Salveaza intreaga configuratie intr-u dictionar pe care il returneaza
    """

    switch_config = {
        "priority": None,
        "interfaces": {},
        "trunk_ports": []
    }
    config_dir = os.path.join(os.path.dirname(__file__), 'configs')
    config_file = os.path.join(config_dir, "switch" + str(SWITCH_ID)+".cfg")

    with open(config_file,'r') as input:
        switch_config["priority"] = int(input.readline().strip())
        for line in input:
            parts = line.strip().split()
            interface_name = parts[0]

            # Vrem sa obtinem si id-ul (indicele) interfetei
            interface_id = None
            for i in range(num_interfaces):
                if get_interface_name(i) == interface_name:
                    interface_id = i
                    break

            vlan_or_type = parts[1]

            if(vlan_or_type == 'T'):
                switch_config["interfaces"][interface_name] = {
                    "id" : interface_id,
                    "type" : "trunk"
                    }
                switch_config["trunk_ports"].append({
                    "id": interface_id,
                    "state": None   # poate fi BLOCKING sau LISTENING 
                })  
            else:
                vlan_id = int(vlan_or_type)
                switch_config["interfaces"][interface_name] = {
                    "id" : interface_id,
                    "type" : "access", 
                    "vlan_id": vlan_id
                    }
        
    return switch_config

def add_vlan_header(data, vlan_id):
    """
        Adauga un header 802.1Q frame-ului cu VLAN ID dat
    """
    ether_type = 0x8200
    vlan_tci = (vlan_id & 0x0FFF)  # Folosim doar ultimii 12 biți pentru VLAN ID
    vlan_header = struct.pack("!HH", ether_type, vlan_tci)
    modified_frame = data[0:12] + vlan_header + data[12:]
    
    return modified_frame
            
def parse_vlan_header(data):
    """
        Extrage VLAN ID dintr-un frame cu header 802.1Q
    """
    ethertype = (data[12] << 8) + data[13]
    if ethertype != 0x8200:
        return None  # Frame-ul nu are header 802.1Q

    # Extragem VLAN TCI
    vlan_tci = int.from_bytes(data[14:16], byteorder='big')
    vlan_id = vlan_tci & 0x0FFF  # Extragem ultimii 12 biti pentru VLAN ID
    return vlan_id


def remove_vlan_header(frame):
    """
        Elimina header-ul 802.1Q dintr-un frame (pentru a fi mai departe trimis pe porturi de tip ACCESS)
    """
    # Verificam daca frame-ul are header 802.1Q (14 bytes Ethernet + 4 bytes VLAN)
    if len(frame) < 18:
        return frame

    ethertype = (frame[12] << 8) + frame[13]
    if ethertype != 0x8200:
        return frame

    # Eliminam header-ul 802.1Q
    frame_without_vlan = frame[:12] + frame[16:]

    return frame_without_vlan

def main():
    # init returns the max interface number. Our interfaces
    # are 0, 1, 2, ..., init_ret value + 1
    switch_id = sys.argv[1]

    num_interfaces = wrapper.init(sys.argv[2:])
    interfaces = range(0, num_interfaces)
    switch_config = parse_switch_config(switch_id, num_interfaces)
    
    # Cream un obiect de tip Switch asociat switch-ului nostru
    switch = Switch(switch_config["priority"], switch_config["trunk_ports"], get_switch_mac())

    # Initializare STP
    switch.set_all_trunk_ports_to_state("BLOCKING")
    if switch.own_bridge_ID == switch.root_bridge_ID:
        switch.set_all_trunk_ports_to_state("LISTENING")

    # Create and start a new thread that deals with sending BDPU
    t = threading.Thread(target=send_bdpu_every_sec, args=(switch,))
    t.start()

    while True:
        interface, data, length = recv_from_any_link()
        dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)

        is_unicast = (dest_mac[0] & 1) == 0

        # Make the MAC src and MAC dst in human readable format
        dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
        src_mac = ':'.join(f'{b:02x}' for b in src_mac)

        # Verificam daca am primit un mesaj BPDU
        if dest_mac == BPDU_DEST_MAC:
            bpdu = switch.deserialize_bpdu(data)
            switch.receive_bpdu(bpdu, interface)
            continue

        CAM_table[src_mac] = interface

        if is_unicast:
            # Adresa MAC destinatie e in tabela CAM
            if dest_mac in CAM_table:
                dest_interface = CAM_table[dest_mac]
                dest_interface_type = switch_config["interfaces"][get_interface_name(dest_interface)]["type"]
                src_interface_type = switch_config["interfaces"][get_interface_name(interface)]["type"]

                if dest_interface_type == "trunk":
                    drop_frame = switch.send_to_trunk_port_unicast(switch_config, dest_interface, src_interface_type, length, data, interface)
                    if drop_frame == -1:
                        continue

                else:
                    drop_frame = switch.send_to_access_port_unicast(switch_config, dest_interface, src_interface_type, length, data, interface, vlan_id)
                    if drop_frame == -1:
                        continue

            else:
                # Adresa MAC destinatie nu e in tabela CAM
                # Facem FLOODING in retea
                switch.send_to_all(switch_config, interface, length, data, interfaces, vlan_id)
                    
        else:
            # BROADCAST
            switch.send_to_all(switch_config, interface, length, data, interfaces, vlan_id)

if __name__ == "__main__":
    main()
