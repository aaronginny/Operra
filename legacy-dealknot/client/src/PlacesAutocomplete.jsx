export const AREAS = [
  // ── UAE · Dubai areas ──────────────────────────────────────────────────────
  "Downtown Dubai", "Dubai Marina", "Jumeirah", "Jumeirah 1", "Jumeirah 2", "Jumeirah 3",
  "Business Bay", "DIFC", "Palm Jumeirah", "Palm Jebel Ali", "Deira", "Bur Dubai",
  "Jumeirah Lake Towers (JLT)", "Jumeirah Village Circle (JVC)", "Jumeirah Village Triangle (JVT)",
  "Al Barsha", "Al Barsha 1", "Al Barsha 2", "Al Barsha South",
  "Dubai Hills Estate", "Arabian Ranches", "Arabian Ranches 2", "Arabian Ranches 3",
  "Motor City", "Sports City", "Studio City", "Mirdif", "Karama", "Oud Metha",
  "Muhaisnah", "Al Qusais", "Al Nahda", "Al Mamzar", "Hor Al Anz",
  "Jumeirah Golf Estates", "Damac Hills", "Damac Hills 2", "Town Square",
  "Silicon Oasis", "Academic City", "International City", "Discovery Gardens",
  "Al Furjan", "Tilal Al Ghaf", "MBR City", "Dubai South", "DIP", "JAFZA",
  "Bluewaters Island", "City Walk", "La Mer", "Marsa Al Arab",
  "Port Rashid", "Al Wasl", "Umm Suqeim", "Al Safa", "Al Manara", "Al Quoz",
  // UAE · Abu Dhabi
  "Al Reem Island, Abu Dhabi", "Yas Island, Abu Dhabi", "Saadiyat Island, Abu Dhabi",
  "Al Khalidiyah, Abu Dhabi", "Corniche, Abu Dhabi", "Al Raha Beach, Abu Dhabi",
  "Masdar City, Abu Dhabi", "Khalifa City, Abu Dhabi", "Mohammed Bin Zayed City, Abu Dhabi",
  "Al Mushrif, Abu Dhabi", "Al Nahyan, Abu Dhabi", "Tourist Club Area, Abu Dhabi",
  // UAE · Other Emirates
  "Sharjah", "Ajman", "Ras Al Khaimah", "Al Ain", "Fujairah", "Umm Al Quwain",

  // ── India · Chennai ────────────────────────────────────────────────────────
  "Adambakkam, Chennai", "Adyar, Chennai", "Alandur, Chennai", "Alwarpet, Chennai",
  "Ambattur, Chennai", "Ambattur Industrial Estate, Chennai", "Anakaputhur, Chennai",
  "Anna Nagar, Chennai", "Anna Nagar East, Chennai", "Anna Nagar Tower, Chennai", "Anna Nagar West, Chennai",
  "Arjun Nagar, Chennai", "Arumbakkam, Chennai", "Ashok Nagar, Chennai",
  "Avadi, Chennai", "Ayanavaram, Chennai", "Aynavaram, Chennai", "Ayyavoo Colony, Chennai",
  "Besant Nagar, Chennai", "Boat Club Road, Chennai",
  "Cathedral Road, Chennai", "Chengalpattu, Chennai", "Chetpet, Chennai",
  "Chinthamani, Chennai", "Chitlapakkam, Chennai", "Choolaimedu, Chennai", "Chromepet, Chennai",
  "Coding Nagar, Chennai", "Dr Radha Krishnan Salai, Chennai",
  "ECR, Chennai", "Egmore, Chennai", "Ekkattuthangal, Chennai", "Ennore, Chennai",
  "Erukkanchery, Chennai",
  "Gerugambakkam, Chennai", "Gopalapuram, Chennai", "Guduvanchery, Chennai", "Guindy, Chennai",
  "Harrington Road, Chennai", "Hasthinapuram, Chennai",
  "Injambakkam, Chennai", "Iyyappanthangal, Chennai",
  "K.K. Nagar, Chennai", "Kadambakkam, Chennai", "Kanathur, Chennai",
  "Kasi Colony, Chennai", "Kathivakkam, Chennai", "Kattankulathur, Chennai", "Kattupakkam, Chennai",
  "Kazhipattur, Chennai", "Kelambakkam, Chennai", "Kellys, Chennai", "Kilpauk, Chennai",
  "Kodambakkam, Chennai", "Kodungaiyur, Chennai", "Kolathur, Chennai",
  "Korattur, Chennai", "Korukkupet, Chennai", "Kotturpuram, Chennai", "Kovalam, Chennai",
  "Kovilambakkam, Chennai", "Koyambedu, Chennai", "Kundanchavadi, Chennai",
  "Luz, Chennai",
  "Madhavaram, Chennai", "Madhavaram Milk Colony, Chennai", "Madipakkam, Chennai",
  "Maduravoyal, Chennai", "Mahindra City, Chennai", "Mamallapuram Road, Chennai",
  "Manali, Chennai", "Manali New Town, Chennai", "Manali Old Town, Chennai",
  "Mandaveli, Chennai", "Maraimalai Nagar, Chennai", "Mathur, Chennai",
  "Medavakkam, Chennai", "Meenambakkam, Chennai", "Minjur, Chennai",
  "Mogappair, Chennai", "Mogappair East, Chennai", "Mogappair West, Chennai",
  "Moolakadai, Chennai", "Mudichur, Chennai", "Mugalivakkam, Chennai",
  "Muttukadu, Chennai", "Mylapore, Chennai",
  "Nandanam, Chennai", "Nanganallur, Chennai", "Nanmangalam, Chennai",
  "Navallur, Chennai", "Neelankarai, Chennai", "Nerkundram, Chennai",
  "Nolambur, Chennai", "Nungambakkam, Chennai",
  "OMR, Chennai", "Okkiyam Thoraipakkam, Chennai", "Old Mahabalipuram Road, Chennai",
  "Old Perungalathur, Chennai", "Otteri, Chennai",
  "Pacific Boulevard, Chennai", "Padappai, Chennai", "Padur, Chennai",
  "Palavakkam, Chennai", "Pallavaram, Chennai", "Pallikaranai, Chennai", "Pammal, Chennai",
  "Park Town, Chennai", "Pattabiram, Chennai", "Peerkankaranai, Chennai",
  "Perambur, Chennai", "Periyar Nagar, Chennai", "Perungalathur, Chennai", "Perungudi, Chennai",
  "Poes Garden, Chennai", "Pondy Bazaar, Chennai", "Poonamallee, Chennai", "Porur, Chennai",
  "Pozhichalur, Chennai", "Purasaiwalkam, Chennai", "Pursaiwalkam, Chennai", "Puzhal, Chennai",
  "Raja Annamalai Puram, Chennai", "Rajakilpakkam, Chennai", "Ramapuram, Chennai",
  "Redhills, Chennai", "Royapettah, Chennai", "Royapuram, Chennai",
  "Saidapet, Chennai", "Saligramam, Chennai", "Selaiyur, Chennai", "Sembakkam, Chennai",
  "Semmanchery, Chennai", "Shanthi Colony, Chennai", "Shenoy Nagar, Chennai",
  "SIDCO Nagar, Chennai", "Singaperumal Koil, Chennai", "Siruseri, Chennai",
  "Sholinganallur, Chennai", "Sowcarpet, Chennai", "St. Thomas Mount, Chennai",
  "T. Nagar, Chennai", "T.V.K. Nagar, Chennai", "Tambaram, Chennai",
  "Teynampet, Chennai", "Thalambur, Chennai", "Thiru Vi Ka Nagar, Chennai",
  "Thirumangalam, Chennai", "Thiruvanmiyur, Chennai", "Thiruvottiyur, Chennai",
  "Thoraipakkam, Chennai", "Thousand Lights, Chennai", "Tittu Village, Chennai",
  "Tondiarpet, Chennai", "Triplicane, Chennai", "TTK Road, Chennai",
  "Ullagaram, Chennai", "Urapakkam, Chennai", "Uthandi, Chennai",
  "Vadapalani, Chennai", "Valasaravakkam, Chennai", "Vandalur, Chennai",
  "Velachery, Chennai", "Vengaivasal, Chennai", "Vepery, Chennai", "Veppamoodu, Chennai",
  "Villivakkam, Chennai", "Virugambakkam, Chennai",
  "Washermanpet, Chennai", "West Mambalam, Chennai", "Wimco Nagar, Chennai",
  "Zamin Pallavaram, Chennai",
  // Chennai · additional areas
  "Aminjikarai, Chennai", "East Mambalam, Chennai", "KK Nagar, Chennai",
  "Mambalam, Chennai",
  "Kottivakkam, Chennai", "Sholinganallur, Chennai", "Perungalathur, Chennai",
  "Alapakkam, Chennai", "Alathur, Chennai", "Ambattur OT, Chennai",
  "Ayyapakkam, Chennai", "Ayappakkam, Chennai",
  "Besant Avenue, Chennai", "Brahmadesam, Chennai",
  "CIT Nagar, Chennai", "CIT Colony, Chennai",
  "Collector Nagar, Chennai", "Cooks Road, Chennai",
  "Duraisamy Nagar, Chennai",
  "Ellis Nagar, Chennai",
  "Gandhi Nagar, Chennai", "Gowrivakkam, Chennai",
  "Hasthinapuram, Chennai",
  "Indira Nagar, Chennai",
  "Jalladampet, Chennai", "Jafferkhanpet, Chennai",
  "Kannagi Nagar, Chennai", "Karapakkam, Chennai", "Keelkattalai, Chennai",
  "Kilkattalai, Chennai", "Kolapakkam, Chennai", "Kottupuram, Chennai",
  "Kumaran Colony, Chennai",
  "Lake Area, Chennai", "Lakshmi Nagar, Chennai", "Lloyds Road, Chennai",
  "Maduvankarai, Chennai", "Mahabhoomi Nagar, Chennai", "Manapakkam, Chennai",
  "Mandaveli, Chennai", "Mangadu, Chennai", "Moovarasampet, Chennai",
  "Mukundapur, Chennai",
  "Nagar, Chennai", "Nandambakkam, Chennai", "Nanmangalam, Chennai",
  "Narayanapuram, Chennai", "Nesapakkam, Chennai", "New Washermanpet, Chennai",
  "Nungambakkam High Road, Chennai",
  "Okkiyampet, Chennai", "Old Pallavaram, Chennai",
  "Padiyanallur, Chennai", "Padi, Chennai", "Pakkam, Chennai",
  "Pallikkaranai, Chennai", "Pambadi, Chennai", "Panayur, Chennai",
  "Perambur Barracks, Chennai", "Periyamet, Chennai",
  "Pudupet, Chennai", "Pudur, Chennai",
  "Raj Bhavan Road, Chennai", "Rajaji Nagar, Chennai",
  "Ramavaram, Chennai", "Ramnagar, Chennai", "Rangarajapuram, Chennai",
  "Roja Nagar, Chennai", "Royale Garden, Chennai",
  "Santhome, Chennai", "Sardar Patel Road, Chennai",
  "Seevaram, Chennai", "Sembarambakkam, Chennai",
  "Sholinganallur, Chennai", "Sithalapakkam, Chennai",
  "Srinivasa Nagar, Chennai", "Subramaniapuram, Chennai",
  "Taramani, Chennai", "Teynampet, Chennai", "Thirumullaivoyal, Chennai",
  "Thiruvika Nagar, Chennai", "Tirumangalam, Chennai",
  "Ullagaram, Chennai", "Unnamalai Nagar, Chennai",
  "Vanagaram, Chennai", "Veppampattu, Chennai", "Vettuvankulam, Chennai",
  "Vijaya Nagar, Chennai", "Vijayanagar, Chennai",
  "West CIT Nagar, Chennai", "West Saidapet, Chennai",
  "Yemmoor, Chennai",
  // India · Mumbai
  "Bandra West, Mumbai", "Bandra East, Mumbai", "Andheri West, Mumbai", "Andheri East, Mumbai",
  "Powai, Mumbai", "Worli, Mumbai", "Lower Parel, Mumbai", "Juhu, Mumbai",
  "Malad West, Mumbai", "Malad East, Mumbai", "Borivali West, Mumbai", "Borivali East, Mumbai",
  "Dadar West, Mumbai", "Dadar East, Mumbai", "Chembur, Mumbai", "Ghatkopar, Mumbai",
  "Vikhroli, Mumbai", "Mulund, Mumbai", "Thane", "Navi Mumbai",
  "Kandivali, Mumbai", "Jogeshwari, Mumbai", "Goregaon, Mumbai",
  "Santacruz West, Mumbai", "Santacruz East, Mumbai", "Vile Parle, Mumbai",
  "Khar, Mumbai", "Colaba, Mumbai", "Cuffe Parade, Mumbai", "Nariman Point, Mumbai",
  "Marine Lines, Mumbai", "Grant Road, Mumbai", "Prabhadevi, Mumbai", "Mahalaxmi, Mumbai",
  "Churchgate, Mumbai", "Fort, Mumbai", "Dharavi, Mumbai", "Kurla, Mumbai",
  "Kalwa, Mumbai", "Airoli, Navi Mumbai", "Vashi, Navi Mumbai", "Kharghar, Navi Mumbai",
  "Nerul, Navi Mumbai", "CBD Belapur, Navi Mumbai", "Panvel, Navi Mumbai",
  // India · Bengaluru
  "Whitefield, Bengaluru", "Koramangala, Bengaluru", "Indiranagar, Bengaluru",
  "HSR Layout, Bengaluru", "Electronic City, Bengaluru", "Hebbal, Bengaluru",
  "Jayanagar, Bengaluru", "JP Nagar, Bengaluru", "Bannerghatta Road, Bengaluru",
  "Sarjapur Road, Bengaluru", "Marathahalli, Bengaluru", "Bellandur, Bengaluru",
  "Outer Ring Road, Bengaluru", "Yeshwanthpur, Bengaluru", "Rajajinagar, Bengaluru",
  "Malleshwaram, Bengaluru", "Basavanagudi, Bengaluru", "RT Nagar, Bengaluru",
  "Yelahanka, Bengaluru", "Devanahalli, Bengaluru", "Kengeri, Bengaluru",
  "Banashankari, Bengaluru", "BTM Layout, Bengaluru", "Bommanahalli, Bengaluru",
  "Kadugodi, Bengaluru", "Hoskote, Bengaluru", "Hennur, Bengaluru",
  "Thanisandra, Bengaluru", "Nagavara, Bengaluru", "Banaswadi, Bengaluru",
  "Kaggadasapura, Bengaluru", "CV Raman Nagar, Bengaluru",
  // India · Hyderabad
  "Banjara Hills, Hyderabad", "Jubilee Hills, Hyderabad", "Gachibowli, Hyderabad",
  "HITEC City, Hyderabad", "Madhapur, Hyderabad", "Kondapur, Hyderabad",
  "Kukatpally, Hyderabad", "Manikonda, Hyderabad", "Narsingi, Hyderabad",
  "Miyapur, Hyderabad", "Bachupally, Hyderabad", "Kompally, Hyderabad",
  "Secunderabad", "Uppal, Hyderabad", "LB Nagar, Hyderabad",
  "Dilsukhnagar, Hyderabad", "Ameerpet, Hyderabad", "SR Nagar, Hyderabad",
  "Begumpet, Hyderabad", "Somajiguda, Hyderabad", "Himayatnagar, Hyderabad",
  "Mehdipatnam, Hyderabad", "Tolichowki, Hyderabad", "Attapur, Hyderabad",
  "Financial District, Hyderabad", "Nanakramguda, Hyderabad",
  // India · Delhi / NCR
  "South Delhi", "North Delhi", "East Delhi", "West Delhi", "Central Delhi",
  "Dwarka, Delhi", "Rohini, Delhi", "Vasant Kunj, Delhi", "Vasant Vihar, Delhi",
  "Saket, Delhi", "Lajpat Nagar, Delhi", "Greater Kailash, Delhi",
  "Defence Colony, Delhi", "Green Park, Delhi", "Hauz Khas, Delhi",
  "Connaught Place, Delhi", "Karol Bagh, Delhi", "Rajouri Garden, Delhi",
  "Janakpuri, Delhi", "Pitampura, Delhi", "Shalimar Bagh, Delhi",
  "Gurgaon", "Cyber City, Gurgaon", "Golf Course Road, Gurgaon",
  "DLF Phase 1-5, Gurgaon", "Sohna Road, Gurgaon", "New Gurgaon",
  "Noida Sector 18", "Noida Sector 62", "Noida Sector 137",
  "Greater Noida", "Noida Extension", "Faridabad", "Ghaziabad",
  // India · Pune
  "Koregaon Park, Pune", "Kalyani Nagar, Pune", "Baner, Pune", "Balewadi, Pune",
  "Wakad, Pune", "Hinjewadi, Pune", "Aundh, Pune", "Kothrud, Pune",
  "Hadapsar, Pune", "Magarpatta, Pune", "Viman Nagar, Pune", "Kharadi, Pune",
  "Kondhwa, Pune", "NIBM Road, Pune", "Camp, Pune", "Deccan, Pune",
  "Shivajinagar, Pune", "Pimpri-Chinchwad, Pune", "Bavdhan, Pune",
  // India · Kolkata
  "Salt Lake, Kolkata", "New Town, Kolkata", "Rajarhat, Kolkata",
  "Ballygunge, Kolkata", "Park Street, Kolkata", "Alipore, Kolkata",
  "Tollygunge, Kolkata", "Behala, Kolkata", "Jadavpur, Kolkata",
  "Howrah", "Dum Dum, Kolkata", "Ultadanga, Kolkata",
  // India · Ahmedabad
  "SG Highway, Ahmedabad", "Prahlad Nagar, Ahmedabad", "Bodakdev, Ahmedabad",
  "Satellite, Ahmedabad", "Vastrapur, Ahmedabad", "Navrangpura, Ahmedabad",
  "Maninagar, Ahmedabad", "Nikol, Ahmedabad", "Gota, Ahmedabad", "Thaltej, Ahmedabad",
  // India · Jaipur
  "Vaishali Nagar, Jaipur", "Mansarovar, Jaipur", "Malviya Nagar, Jaipur",
  "C-Scheme, Jaipur", "Tonk Road, Jaipur", "Jagatpura, Jaipur", "Ajmer Road, Jaipur",
  // India · Kochi
  "Kakkanad, Kochi", "Edapally, Kochi", "Vyttila, Kochi", "Aluva, Kochi",
  "Marine Drive, Kochi", "MG Road, Kochi", "Panampilly Nagar, Kochi",
  "Thrippunithura, Kochi", "Thrissur",
  // India · Coimbatore
  "RS Puram, Coimbatore", "Gandhipuram, Coimbatore", "Saibaba Colony, Coimbatore",
  "Peelamedu, Coimbatore", "Singanallur, Coimbatore", "Vadavalli, Coimbatore",
  "Hopes College, Coimbatore", "Kovaipudur, Coimbatore", "Thudiyalur, Coimbatore",
  "Ondipudur, Coimbatore", "Podanur, Coimbatore", "Ganapathy, Coimbatore",
  "Kuniyamuthur, Coimbatore", "Sulur, Coimbatore", "Mettupalayam Road, Coimbatore",
  "Avinashi Road, Coimbatore", "Race Course, Coimbatore", "Town Hall, Coimbatore",
  "Tatabad, Coimbatore", "Sowripalayam, Coimbatore", "Vellingiri Road, Coimbatore",
  "Kalapatti, Coimbatore", "Chinnavedampatti, Coimbatore", "Saravanampatty, Coimbatore",
  "Vilankurichi, Coimbatore", "Koil Medu, Coimbatore", "Nehru Nagar, Coimbatore",
  "Sidhapudur, Coimbatore", "Ramanathapuram, Coimbatore", "Velandipalayam, Coimbatore",
  // India · Madurai
  "Madurai", "Anna Nagar, Madurai", "KK Nagar, Madurai", "Thirunagar, Madurai",
  "Iyer Bungalow, Madurai", "Bypass Road, Madurai", "Vilangudi, Madurai",
  "Arasaradi, Madurai", "Kalavasal, Madurai", "Simmakkal, Madurai",
  "Tallakulam, Madurai", "Palanganatham, Madurai", "Surveyor Colony, Madurai",
  "Teppakulam, Madurai", "Narimedu, Madurai", "Alagar Kovil Road, Madurai",
  "Kochadai, Madurai", "Madurai South, Madurai", "Madurai North, Madurai",
  "Othakadai, Madurai", "Melur Road, Madurai",
  // India · Tiruchirappalli
  "Tiruchirappalli", "Thillai Nagar, Tiruchirappalli", "Cantonment, Tiruchirappalli",
  "Srirangam, Tiruchirappalli", "KK Nagar, Tiruchirappalli", "Woraiyur, Tiruchirappalli",
  "Ariyamangalam, Tiruchirappalli", "Ponmalai, Tiruchirappalli", "Puthur, Tiruchirappalli",
  "Tennur, Tiruchirappalli", "Karumandapam, Tiruchirappalli", "Khajamalai, Tiruchirappalli",
  "Pallakkarai, Tiruchirappalli", "Mannarpuram, Tiruchirappalli", "Golden Rock, Tiruchirappalli",
  // India · Salem
  "Salem", "Fairlands, Salem", "Swarnapuri, Salem", "Alagapuram, Salem",
  "Shevapet, Salem", "Gugai, Salem", "Hasthampatti, Salem", "Suramangalam, Salem",
  "Kondalampatti, Salem", "Ammapet, Salem", "Four Roads, Salem", "Five Roads, Salem",
  "Meyyanur, Salem", "Srinivasa Nagar, Salem", "Kitchipalayam, Salem",
  // India · Tirunelveli
  "Tirunelveli", "Palayamkottai, Tirunelveli", "Melapalayam, Tirunelveli",
  "Vannarpet, Tirunelveli", "Pettai, Tirunelveli", "Ambasamudram, Tirunelveli",
  "Nanguneri, Tirunelveli", "Cheranmahadevi, Tirunelveli",
  // India · Erode
  "Erode", "Perundurai, Erode", "Bhavani, Erode", "Thindal, Erode",
  "Veerappampalayam, Erode", "Sivagiri, Erode", "Gobichettipalayam, Erode",
  // India · Vellore
  "Vellore", "Katpadi, Vellore", "Sathuvachari, Vellore", "Bagayam, Vellore",
  "Virudhambut, Vellore", "Gandhi Nagar, Vellore",
  // India · Tiruppur
  "Tiruppur", "Avinashi, Tiruppur", "Mangalam, Tiruppur", "Palladam, Tiruppur",
  "Veerapandi, Tiruppur", "Dharapuram, Tiruppur",
  // India · Kanchipuram
  "Kanchipuram", "Sriperumbudur, Kanchipuram", "Oragadam, Kanchipuram",
  "Walajabad, Kanchipuram", "Uthiramerur, Kanchipuram",
  // India · Thanjavur
  "Thanjavur", "Kumbakonam, Thanjavur", "Papanasam, Thanjavur",
  "Pattukkottai, Thanjavur", "Patteeswaram, Thanjavur",
  // India · Tiruvannamalai
  "Tiruvannamalai", "Vellore Road, Tiruvannamalai", "Polur, Tiruvannamalai", "Cheyyar, Tiruvannamalai",
  // India · Puducherry
  "Puducherry", "White Town, Puducherry", "Lawspet, Puducherry", "Mudaliarpet, Puducherry",
  "Villianur, Puducherry", "Ariyankuppam, Puducherry", "Ozhukarai, Puducherry",
  "Reddiarpalayam, Puducherry", "Thattanchavady, Puducherry",
  // India · Hosur
  "Hosur", "Mathigiri, Hosur", "Sipcot, Hosur", "Kelamangalam, Hosur",
  // India · Dindigul
  "Dindigul", "Palani, Dindigul", "Oddanchatram, Dindigul", "Natham, Dindigul",
  // India · Cuddalore
  "Cuddalore", "Chidambaram, Cuddalore", "Panruti, Cuddalore", "Neyveli, Cuddalore",
  // India · Nagapattinam
  "Nagapattinam", "Mayiladuthurai, Nagapattinam", "Sirkazhi, Nagapattinam", "Velankanni, Nagapattinam",
  // India · Virudhunagar
  "Virudhunagar", "Sivakasi, Virudhunagar", "Rajapalayam, Virudhunagar", "Aruppukkottai, Virudhunagar",
  // India · Thoothukudi
  "Thoothukudi", "Kovilpatti, Thoothukudi", "Kayalpatnam, Thoothukudi", "Tiruchendur, Thoothukudi",
  // India · Krishnagiri
  "Krishnagiri", "Denkanikottai, Krishnagiri", "Bargur, Krishnagiri", "Pochampalli, Krishnagiri",
  // India · Dharmapuri
  "Dharmapuri", "Harur, Dharmapuri", "Palacode, Dharmapuri", "Pennagaram, Dharmapuri",
  // India · Namakkal
  "Namakkal", "Tiruchengode, Namakkal", "Rasipuram, Namakkal", "Senthamangalam, Namakkal",
  // India · Karur
  "Karur", "Aravakurichi, Karur", "Kulithalai, Karur", "Krishnarayapuram, Karur",
  // India · Perambalur
  "Perambalur", "Ariyalur, Perambalur", "Jayankondam, Perambalur",
  // India · Sivaganga
  "Sivaganga", "Devakottai, Sivaganga", "Karaikudi, Sivaganga", "Manamadurai, Sivaganga",
  // India · Ramanathapuram
  "Ramanathapuram", "Paramakudi, Ramanathapuram", "Rameswaram, Ramanathapuram", "Mandapam, Ramanathapuram",
  // India · Theni
  "Theni", "Uthamapalayam, Theni", "Bodinayakanur, Theni", "Periyakulam, Theni",
  // India · Nilgiris
  "Nilgiris", "Ooty, Nilgiris", "Coonoor, Nilgiris", "Kotagiri, Nilgiris", "Gudalur, Nilgiris",
  // India · Kanniyakumari
  "Kanniyakumari", "Nagercoil, Kanniyakumari", "Marthandam, Kanniyakumari",
  "Colachel, Kanniyakumari", "Thuckalay, Kanniyakumari",
  // India · Tenkasi
  "Tenkasi", "Sankarankovil, Tenkasi", "Kadayanallur, Tenkasi", "Courtallam, Tenkasi",
  // India · Chengalpattu
  "Chengalpattu", "Tambaram, Chengalpattu", "Vandalur, Chengalpattu", "Padappai, Chengalpattu",
  "Maraimalai Nagar, Chengalpattu", "Guduvanchery, Chengalpattu", "Singaperumal Koil, Chengalpattu",
  "Kattankulathur, Chengalpattu", "Mahindra City, Chengalpattu", "Urapakkam, Chengalpattu",
  "Perungalathur, Chengalpattu",
  // India · Ranipet
  "Ranipet", "Arcot, Ranipet", "Walajapet, Ranipet", "Sholinghur, Ranipet",
  // India · Tirupattur
  "Tirupattur", "Vaniyambadi, Tirupattur", "Ambur, Tirupattur", "Jolarpet, Tirupattur",
  // India · Kallakurichi
  "Kallakurichi", "Ulundurpet, Kallakurichi", "Sankarapuram, Kallakurichi", "Chinnasalem, Kallakurichi",
  // India · Villupuram
  "Villupuram", "Tindivanam, Villupuram", "Gingee, Villupuram", "Vikravandi, Villupuram",
  // India · Tiruvarur
  "Tiruvarur", "Mannargudi, Tiruvarur", "Papanasam, Tiruvarur", "Nannilam, Tiruvarur",
  // India · Other cities
  "Surat", "Vadodara", "Indore", "Bhopal", "Nagpur", "Nashik", "Aurangabad",
  "Visakhapatnam", "Vijayawada", "Tirupati",
  "Chandigarh", "Mohali", "Panchkula", "Ludhiana", "Amritsar", "Jalandhar",
  "Patna", "Bhubaneswar", "Raipur", "Ranchi", "Guwahati",
  "Thiruvananthapuram", "Kozhikode", "Kannur",

  // ── UK · London ────────────────────────────────────────────────────────────
  "Mayfair, London", "Chelsea, London", "Kensington, London", "Knightsbridge, London",
  "Canary Wharf, London", "Shoreditch, London", "Islington, London",
  "Notting Hill, London", "Belgravia, London", "Westminster, London",
  "Marylebone, London", "Fitzrovia, London", "Soho, London", "Covent Garden, London",
  "Bermondsey, London", "Southwark, London", "Battersea, London", "Clapham, London",
  "Brixton, London", "Peckham, London", "Hackney, London", "Dalston, London",
  "Stoke Newington, London", "Walthamstow, London", "Stratford, London",
  "Canary Wharf, London", "Greenwich, London", "Lewisham, London",
  "Wimbledon, London", "Richmond, London", "Kingston, London", "Croydon, London",
  "Ealing, London", "Hammersmith, London", "Fulham, London", "Putney, London",
  "Barnes, London", "Shepherd's Bush, London", "Acton, London",
  "Wembley, London", "Harrow, London", "Edgware, London",
  "Finchley, London", "Barnet, London", "Enfield, London",
  // UK · Other cities
  "Manchester", "Birmingham", "Leeds", "Edinburgh", "Glasgow",
  "Bristol", "Liverpool", "Sheffield", "Newcastle", "Nottingham",
  "Leicester", "Southampton", "Portsmouth", "Brighton", "Oxford", "Cambridge",

  // ── Singapore ──────────────────────────────────────────────────────────────
  "Orchard, Singapore", "Marina Bay, Singapore", "Sentosa, Singapore",
  "CBD, Singapore", "Tanjong Pagar, Singapore", "River Valley, Singapore",
  "Bukit Timah, Singapore", "Holland Village, Singapore", "Novena, Singapore",
  "Bishan, Singapore", "Ang Mo Kio, Singapore", "Toa Payoh, Singapore",
  "Jurong East, Singapore", "Jurong West, Singapore", "Clementi, Singapore",
  "Queenstown, Singapore", "Buona Vista, Singapore", "One-North, Singapore",
  "Tampines, Singapore", "Pasir Ris, Singapore", "Bedok, Singapore",
  "Woodlands, Singapore", "Yishun, Singapore", "Sengkang, Singapore",
  "Punggol, Singapore", "Hougang, Singapore", "Serangoon, Singapore",

  // ── USA ────────────────────────────────────────────────────────────────────
  "Manhattan, New York", "Brooklyn, New York", "Queens, New York",
  "Upper East Side, New York", "Upper West Side, New York", "SoHo, New York",
  "Tribeca, New York", "Financial District, New York", "Midtown, New York",
  "Williamsburg, New York", "Astoria, New York",
  "Beverly Hills, Los Angeles", "Santa Monica, Los Angeles", "West Hollywood, Los Angeles",
  "Venice, Los Angeles", "Malibu, Los Angeles", "Brentwood, Los Angeles",
  "Downtown LA", "Pasadena", "Burbank",
  "Downtown Chicago", "Lincoln Park, Chicago", "River North, Chicago",
  "Wicker Park, Chicago", "Gold Coast, Chicago",
  "South Beach, Miami", "Brickell, Miami", "Wynwood, Miami", "Coconut Grove, Miami",
  "Coral Gables, Miami", "Aventura, Miami",
  "Pacific Heights, San Francisco", "Nob Hill, San Francisco", "Mission, San Francisco",
  "SOMA, San Francisco", "Castro, San Francisco", "Marina, San Francisco",
  "Palo Alto", "Mountain View", "Sunnyvale", "San Jose",
  "Downtown Seattle", "Capitol Hill, Seattle", "Bellevue, Seattle",
  "Back Bay, Boston", "Beacon Hill, Boston", "Cambridge, Boston",
  "Capitol Hill, Washington DC", "Georgetown, Washington DC", "Dupont Circle, Washington DC",
  "Uptown, Dallas", "Highland Park, Dallas", "Plano, Dallas",
  "Montrose, Houston", "River Oaks, Houston", "The Woodlands, Houston",
  "Buckhead, Atlanta", "Midtown Atlanta", "Scottsdale, Arizona",

  // ── Australia ─────────────────────────────────────────────────────────────
  "CBD, Sydney", "North Sydney", "Bondi, Sydney", "Surry Hills, Sydney",
  "Newtown, Sydney", "Glebe, Sydney", "Pyrmont, Sydney", "Darlinghurst, Sydney",
  "Mosman, Sydney", "Manly, Sydney", "Parramatta, Sydney",
  "CBD, Melbourne", "Southbank, Melbourne", "St Kilda, Melbourne", "South Yarra, Melbourne",
  "Richmond, Melbourne", "Fitzroy, Melbourne", "Carlton, Melbourne",
  "Docklands, Melbourne", "Brighton, Melbourne",
  "CBD, Brisbane", "Fortitude Valley, Brisbane", "New Farm, Brisbane", "Paddington, Brisbane",
  "CBD, Perth", "Subiaco, Perth", "Fremantle, Perth", "Cottesloe, Perth",
  "Adelaide", "Gold Coast", "Sunshine Coast",

  // ── Canada ────────────────────────────────────────────────────────────────
  "Downtown Toronto", "Yorkville, Toronto", "King West, Toronto",
  "Scarborough, Toronto", "Mississauga", "Brampton",
  "Downtown Vancouver", "Yaletown, Vancouver", "Gastown, Vancouver",
  "West Vancouver", "North Vancouver", "Burnaby", "Richmond, BC",
  "Plateau-Mont-Royal, Montreal", "Griffintown, Montreal", "Old Montreal",
  "Downtown Calgary", "Beltline, Calgary",

  // ── Hong Kong ─────────────────────────────────────────────────────────────
  "Central, Hong Kong", "Wan Chai, Hong Kong", "Causeway Bay, Hong Kong",
  "North Point, Hong Kong", "Quarry Bay, Hong Kong", "Taikoo, Hong Kong",
  "Tsim Sha Tsui, Kowloon", "Mong Kok, Kowloon", "Yau Ma Tei, Kowloon",
  "Sha Tin, New Territories", "Tuen Mun, New Territories",
  "Discovery Bay, Hong Kong", "Lantau, Hong Kong",

  // ── GCC / MENA ────────────────────────────────────────────────────────────
  "Riyadh", "Jeddah", "NEOM, Saudi Arabia", "Dammam", "Khobar",
  "Kuwait City", "Salmiya, Kuwait", "Fintas, Kuwait",
  "Doha", "The Pearl, Doha", "West Bay, Doha", "Lusail, Doha",
  "Muscat", "Qurum, Muscat", "Al Mouj, Muscat",
  "Manama", "Seef, Bahrain", "Amwaj, Bahrain",
  "Cairo", "New Cairo", "6th of October, Cairo", "Heliopolis, Cairo",
  "Beirut", "Amman",

  // ── Europe ────────────────────────────────────────────────────────────────
  "Paris", "Le Marais, Paris", "Saint-Germain-des-Prés, Paris", "Champs-Élysées, Paris",
  "Berlin", "Mitte, Berlin", "Prenzlauer Berg, Berlin", "Charlottenburg, Berlin",
  "Frankfurt", "Munich", "Hamburg", "Cologne", "Düsseldorf", "Stuttgart",
  "Amsterdam", "Zurich", "Geneva", "Basel",
  "Madrid", "Barcelona", "Valencia", "Seville",
  "Milan", "Rome", "Florence", "Venice",
  "Lisbon", "Porto",
  "Dublin", "Vienna", "Prague", "Warsaw", "Stockholm", "Copenhagen", "Oslo",
];

const LIST_ID = "dk-areas-list";

export default function PlacesAutocomplete({ value, onChange, placeholder = "Search city, area, neighbourhood…" }) {
  return (
    <>
      <datalist id={LIST_ID}>
        {AREAS.map((a) => <option key={a} value={a} />)}
      </datalist>
      <input
        list={LIST_ID}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
      />
    </>
  );
}
