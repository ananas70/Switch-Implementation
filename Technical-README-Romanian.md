## Descriere

### Structuri de date folosite

* Am creat o clasa **Switch** care contine atribute specifice unui switch (`priority_value`, `ports`, `MAC_address`) precum si metode utile pentru aflarea informatiilor despre porturi, procesarea frame-urilor BPDU sau trimiterea frame-urilor in general.
* Am creat o clasa **BPDU** pentru a stoca date utile pentru mesajele BPDU: `root_bridge_ID`, `sender_bridge_ID` si `root_path_cost`. In implementarea mea, mesajele BPDU sunt structurate astfel: Header Ethernet + Header LLC + cele 3 campuri mentionate mai sus (fiecare pe cate 4 octeti) folosite in procesul STP.
* Am creat un dictionar asociat tabelei de comutare a switch-ului - `CAM_table`, stocata ca variabila globala.
* Am salvat configuratia citita pentru fiecare switch intr-un dictionar cu campurile `priority`, `interfaces` si `trunk_ports`. `interfaces` contine id-ul si tipul (*trunk* sau *access*) al fiecarei interfete, iar `trunk_ports` a fost implementat pentru cerinta 3 - STP si contine campurile: `id` si `state`: id-ul si starea unei interfete de tip *trunk*.

### Implementare

In metoda `main`, inainte de a intra in bucla infinita destinata primirii frame-urilor, executam urmatoarele:

* Parsam fisierul cu configuratia switch-ului si salvam in dictionarul nostru - `switch_config`.
* Pornim procesul STP, setand starile porturilor switch-ului si apeland in paralel metoda `send_bdpu_every_sec` care primeste ca argument obiectul curent de tip `Switch`.

In bucla infinita procedam astfel:

- Folosim ca schelet blocul de pseudocod dat in descrierea temei pentru procesul de forwarding.
- Prioritate au mesajele BPDU - pe acestea le procesam inainte, verificand adresa MAC destinatie. Daca primim un frame BPDU, apelm metoda `receive_bpdu`.
- Daca nu am primit un frame BPDU, continuam procesul de forwarding. Actualizam tabela MAC.
- Mai departe, procesul de forwarding se desfasoara dupa urmatorul pseudocod:
    - Daca frame-ul primit are destinatie unicast:
        - Daca exista o intrare pentru destinatia MAC in tabela de comutare, verificam tipul portului pe care urmeaza sa trimitem frame-ul:
            - Daca este de tip *trunk*, verificam tipul portului pe care a ajuns frame-ul (portul-sursa).
                - Daca portul-sursa este de tip *trunk*, atunci trimitem frame-ul direct pe legatura.
                - Daca portul-sursa este de tip *access*, atunci adaugam header-ul 802.1Q si dupa aceea trimitem frame-ul.
            - Daca este de tip *access*, verificam tipul portului pe care a ajuns frame-ul (portul-sursa).
                - Daca portul-sursa este de tip *trunk*, atunci comparam tag-ul VLAN ID cu VLAN ID-ul portului de tip access. Daca acestea nu coincid, dam drop.
                - Daca portul-sursa este de tip *access*, atunci comparam VLAN ID-urile (cel al destinatiei si cel al sursei). Daca sunt diferite, dam drop.
        - Daca nu exista o intrare pentru destinatia MAC in tabela de comutare, facem flooding. Verificam tipul portului pe care a ajuns frame-ul (portul-sursa):
            - Daca portul-sursa este de tip *access*, atunci trimitem i) pe restul interfetelor de tip *access* care au acelasi VLAN ID si ii) pe toate interfetele trunk (care nu au fost blocate in urma procesului STP) dar dupa ce adaugam header-ul 802.1Q.
            - Daca portul-sursa este de tip *trunk*, atunci trimitem i) pe toate interfetele de tip *access* care au acelasi VLAN ID cu tag-ul din frame dar dupa ce eliminam header-ul 802.1Q si ii) pe toate interfetele de tip *trunk* (pastrand header-ul 802.1Q).
    
    - Daca frame-ul primit are destinatie broadcast, procedam la fel ca in cazul in care facem flooding, atunci cand nu avem intrare in tabela de comutare.

- Pentru cerinta 3, in implementarea protocolului STP, am luat in considerare prioritatea din fisierul de configuratie al fiecarui switch pentru a stabili root bridge-ul si am folosit doar 2 stari asociate porturilor switch-ului : `LISTENING` si `BLOCKING`. Porturile cu stare `BLOCKING` sunt porturile asociate legaturilor redundante si nu receptioneaza trafic.

