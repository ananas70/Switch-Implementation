# A Switch Implementation in Python

## Overview

This project implements a software-defined switch with **Spanning Tree Protocol (STP)** support. The switch processes Ethernet frames, manages VLANs, and prevents network loops by exchanging **BPDU (Bridge Protocol Data Units)**.

## Features

- **BPDU Handling:** Sends, receives, serializes, and deserializes BPDU packets.
- **Root Bridge Election:** Determines the root switch based on priority.
- **Port State Management:** Sets ports to **BLOCKING** or **LISTENING** to prevent loops.
- **VLAN Support:** Handles VLAN-tagged and untagged frames.
- **CAM Table Learning:** Learns and forwards frames based on MAC addresses.

## How It Works

1. **BPDU Exchange:**  
   - If the switch is the root, it sends BPDU frames periodically.
   - If it receives a superior BPDU, it updates its root bridge and recalculates port states.
   
2. **Frame Forwarding:**  
   - Uses the **CAM table** to forward frames efficiently.
   - Implements **flooding** when the destination is unknown.

3. **VLAN Handling:**  
   - **Trunk Ports:** Forward tagged frames between VLANs.
   - **Access Ports:** Strip VLAN tags before sending frames to end devices.

## Code Structure

- `Switch` class: Implements STP logic, BPDU handling, and forwarding.
- `BPDU` class: Defines BPDU packet structure and serialization.
- `parse_switch_config()`: Parses the switch configuration file.
- `send_bdpu_every_sec()`: Periodically sends BPDUs.

