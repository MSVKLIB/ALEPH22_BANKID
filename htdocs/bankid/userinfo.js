//parameters - settings
//
//
// Set Userinfo / Profile URL
//const userInfoEndpoint = 'https://oidc.sandbox.bankid.cz/profile'; //Sandbox
const userInfoEndpoint = 'https://oidc.bankid.cz/profile'; //Production

// path to backend script
const backend = '/cgi-bin/bankid.cgi';
const backendFileUpload = '/cgi-bin/bankid_file.cgi';



const processEl=document.getElementById('process'); //element for responses from service to user and forms for registration and password

// You must have a valid access token
const thisURI = window.location.href;
var  accessToken = '';
if ( thisURI.match(/access_token=[^&]+/)) {
   accessToken = thisURI.match(/access_token=[^&]+/)[0].replace('access_token=','');
   }
else { ExceptionError('URI does not contain access_token','error'); }
console.log('DEBUG accessToken is '+accessToken);

//call msvk cgi to write token
MsvkCallStart(accessToken).then(
   function(value) {
console.log('value is '+value);
      if ( ! value ) { ExceptionError('Error in backend call start response','U'); return 0; }  //unverified
      else { 
         //presmerovani na bankid
         fetchUserinfo();
         }
      },
   function(error) { ExceptionError('Error in backend call start :'+error, 'error'); return 0; }
   );


//for posting data fetch see https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch
//for nested fetch see https://www.pluralsight.com/guides/handling-nested-http-requests-using-the-fetch-api


const fetchUserinfo = async () => {
  // Pass access token to authorization header
  const headers = { Authorization: 'Bearer ' + accessToken, };

  try {
    const res = await fetch(userInfoEndpoint, { headers });
    // Retrieved userinfo / profile data in object format
    const json = await res.json();  
console.log('<p>email is '+json.email+'</p>'); //DEBUG TODO
window.debug=json;
    window.hasMail = json.email ? 1 : 0; //kontrola jestli ma email
    //window.borName = json.given_name+' '+json.family_name;
    //window.borName = json.bor_login;
    let plifxml = MsvkBankidJson2PlifXml(json);
console.log('plifxml is '+plifxml);

    //call msvk cgi step 2 - check
	//ren - když chybí v json adresa, plifxml == 0, chyba ošetřena, není třeba volat MsvkCallCheck
    //   MsvkCallCheck(accessToken,plifxml);
	if (plifxml !== 0) { MsvkCallCheck(accessToken, plifxml); } //ren
  } catch (ex) { // handle errors
    ExceptionError(ex, 'error');
  }
};

//msvk
//window.patron_found=0;
async function MsvkCallStart(token) {
console.log('DEBUG MsvkCallStart, token is '+token);
  let url = backend+'?func=start&token='+token;
  let resp = await fetch(url);
  let json = await resp.json();
//  json = utf8.decode(json));
  if ( json.response == 'ok' ) {return true;}
  else if ( json.response == 'error' ) { ExceptionError( json.text, 'error' ); }
  else { ExceptionError( 'unercognised error in response in MsvkCallStart', 'error' ); }
  return false;
  }

async function MsvkCallCheck(token,patron) {
console.log('DEBUG MsvkCallCheck with param patron: '+patron);
   let url = backend;
   let resp = await fetch(url,  { method: "POST", cache: "no-cache", credentials: "same-origin", headers: {  Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}, body: 'func=check&token='+token+'&patron='+patron }  );
   let json = await resp.json();
   //platna registrace
   if ( json.response == "registration_valid" ) {
      let expiry_date='';
      if ( json.text.match(/[0-9]{8}/) )  { 
         let eday=json.text.substr(6,2); eday=eday.replace(/^0/,'');
         let emonth=json.text.substr(4,2); emonth=emonth.replace(/^0/,'');
         expiry_date = eday+'.&nbsp;'+emonth+'.&nbsp;'+json.text.substr(0,4);
         }
      ( document.querySelector('#expiry_date') || document.createElement('span') ).innerHTML = expiry_date;
      ( document.querySelector('#expiry_days_before') || document.createElement('span') ).innerHTML = json.daysbefore;
      document.querySelector('#valid_registration').style.display = '';
      }
   // pod stanoveny vek 
   else if ( json.response == "too young" ) {
      ( document.querySelector('#minimal_age') || document.createElement('span') ).innerHTML = json.age_limit;
      document.querySelector('#too_young').style.display = '';
      }
   // ctenar existuje v alephu
   else if ( json.response == "found" ) {
//      window.patron_found=1;
      let registrationFee = json.registration_fee; registrationFee = registrationFee.replace(/00$/,',-'); registrationFee = registrationFee.replace(/(\d\d)$/ ,',$1');
      window.registrationFee = json.registration_fee; 
      ( document.querySelector('#registration_fee') || document.createElement('span') ).appendChild ( document.createTextNode(registrationFee) );
      if ( json.registration_fee.match(/^\s*0+\s*$/ ) ) { (document.querySelector('#registration_fee_note') || document.createElement('span') ).style.display = 'none';
  	    document.querySelector('#ztp').style.display='none';
        }
      ( document.querySelector('#patron_status') || document.createElement('span') ).appendChild ( document.createTextNode(json.bor_status_name) );
      ( document.querySelector('#login') || document.createElement('span') ).appendChild ( document.createTextNode(json.bor_login) );
      //document.querySelector('#password_change_button').style.display='none';
      document.querySelector('#change_password').style.display='';
      //document.querySelector('#password_line1').style.display='none';
      //document.querySelector('#password_line2').style.display='none';
      document.querySelector('#patron_found').style.display = '';
      if ( ! window.hasMail ) { 
         if ( json.bor_id ) { getMailAleph(json.bor_id); }
         else { document.querySelector('#setMail').style.display = ''; } //input pro mail, pokud hobankid nema
         }
      }
   // novy ctenar 
   else if ( json.response == "new" ) {
console.log ('new patron');
      let registrationFee = json.registration_fee; registrationFee = registrationFee.replace(/00$/,',-'); registrationFee = registrationFee.replace(/(\d\d)$/ ,',$1');
      window.registrationFee = json.registration_fee; 
      ( document.querySelector('#registration_fee') || document.createElement('span') ).appendChild ( document.createTextNode(registrationFee) );
      if ( json.registration_fee.match(/^\s*0+\s*$/ ) ) { (document.querySelector('#registration_fee_note') || document.createElement('span') ).style.display = 'none';
	    document.querySelector('#ztp').style.display='none';
	    }
      ( document.querySelector('#patron_status') || document.createElement('span') ).appendChild ( document.createTextNode(json.bor_status_name) );
      ( document.querySelector('#login') || document.createElement('span') ).appendChild ( document.createTextNode(json.bor_login) );
      document.querySelector('#password_change_button').style.display='none';
      document.querySelector('#change_password').style.display='';
      //document.querySelector('#patron_new').....
      document.querySelector('#patron_found').style.display='';
      if ( ! window.hasMail ) { document.querySelector('#setMail').style.display = ''; } //input pro mail, pokud hobankid nema
      }
   else { 
      //ExceptionError('Unrecognised JSON response: '+json.response+')','error');//ren
      ExceptionError('Unrecognised JSON response: '+json.response,'error');
	  }
   }


async function MsvkCallRegistrate() {
console.log('DEBUG MsvkCallRegistrate');
   document.querySelector('#souhlas_kr').style.outline = '';
   document.querySelector('#souhlas_ou').style.outline = '';
   document.querySelector('#password1').style.border = '';
   document.querySelector('#password2').style.border = '';
   document.querySelector('#email').style.border = '';
   //overit zadana data
   let ra=document.querySelectorAll('[id^=registration_alert]');
   for (let i=0; i<ra.length; i++) { ra[i].style.display='none'; }
   if ( ! document.querySelector('#souhlas_kr').checked ) { 
      document.querySelector('#registration_alert_kr').style.display=''; 
      document.querySelector('#souhlas_kr').style.outline = '2px solid red';
      return 0;
      }
   if ( ! document.querySelector('#souhlas_ou').checked ) { 
      document.querySelector('#registration_alert_ou').style.display=''; 
      document.querySelector('#souhlas_ou').style.outline = '2px solid red';
      return 0;
      }
 //  if ( ! window.patron_found ) {
      if ( document.querySelector('#password1').value == '' ) { 
         document.querySelector('#registration_alert_no_pass').style.display=''; 
         document.querySelector('#password1').style.border = '2px solid red';
         return 0;
         }
      if ( document.querySelector('#password2').disabled == false && document.querySelector('#password1').value != document.querySelector('#password2').value ) { 
      //if ( document.querySelector('#password_show').checked == false && document.querySelector('#password1').value != document.querySelector('#password2').value ) { 
         document.querySelector('#registration_alert_pass_diff').style.display=''; 
         document.querySelector('#password2').style.border = '2px solid red';
         return 0;
         }   
      //check hesla min 3 chars Mat. 20230801
      if ( document.querySelector('#password1').value.length < 3 ) {
         document.querySelector('#registration_alert_pass_short').style.display='';
         document.querySelector('#password2').style.border = '2px solid red';
         return 0;
         }
     //check emailu Mat. 20230801
     if ( document.querySelector('#email').value.length > 0 ) { 
        if ( !(document.querySelector('#email').value.match(/^\s*.+@.+\..+/)) ) {
           document.querySelector('#registration_alert_email_syntax').style.display='';
           document.querySelector('#email').style.border = '2px solid red';
           return 0;
           }
        }
//TODO asas
 //     }  //ren heslo musí vyplnit i známý patron
   //hide button registrate
   (document.querySelector('#registrate_button') || document.createElement('span')).style.display='none';
   //call backend
   let password=document.querySelector('#password1').value;
   let userEmail=document.querySelector('#email').value;
   //console.log('userEmail '+userEmail);
   let url = backend;
   try {
      //let callBody =  'func=registrate&token='+accessToken+'&password='+password;
      let formData = new FormData();
      formData.append("func", "registrate");
      formData.append("token", accessToken);
      formData.append("password", password);
      formData.append("email", userEmail); //ren
      let resp = await fetch(url,  { method: "POST", cache: "no-cache", credentials: "same-origin", body: formData }  );
      let json = await resp.json();
      if ( json.response == "ok" ) {
         if ( window.ztp_uploaded ) { 
            if ( window.ztp_uploaded == 'ok' ) { document.querySelector('#registration_success_ztp').style.display=''; }
            else { document.querySelector('#registration_success_ztp_error_upload').style.display=''; }
            }
         else {
            document.querySelector('#registration_success').style.display='';
            if ( typeof window.registrationFee != 'undefined') { if ( window.registrationFee.match(/^\s*0+\s*$/) &&  document.querySelector('#registration_success_zdarma')) {
               document.querySelector('#registration_success').style.display='none';
               document.querySelector('#registration_success_zdarma').style.display='';
               } }
            }
         }
      else {
         if ( json.response == "error" )  { document.querySelector('#registration_error_text').appendChild ( document.createTextNode('('+json.text+')') );}
         document.querySelector('#registration_error').style.display='';
//         document.querySelector('#patron_found').style.display='none';
         }
      } 
   catch (ex) { // handle errors
      ExceptionError(ex, 'error');
      }
   }





function MsvkBankidJson2PlifXml ( json ) {
console.log('DEBUG MsvkBankidJson2PlifXml');
	
   //converts json from BankId to xml in Patrlon Loader for upload to aleph api
   //input: bankid json, returns xml

//TODO DEBUG for sandbox / doplneni adresy
//json.email='mail@ho.ho'; json.title_prefix='PuDr.'; json.addresses=new Array(); json.addresses.push(''); json.addresses[0].street='Vedlejsi'; json.addresses[0].streetnumber='0'; json.addresses[0].evidencenumber='1'; json.addresses[0].city='Atlantis'; json.addresses[0].zipcode='ZZZ'; aa.
//json.email='mail@ho.ho'; json.title_prefix='PuDr.'; json.addresses=new Array(); let aa=new Object(); aa.street='Vedlejsi'; aa.streetnumber='0'; aa.evidencenumber='1'; aa.city='Atlantis'; aa.zipcode='ZZZ'; aa.cityarea='undergroud'; json.addresses.push(aa);

   let plif = new Document();
   plif.appendChild ( CreateElement('p-file-20',null) );
   plif.getElementsByTagName('p-file-20')[0].appendChild ( CreateElement('patron-record',null) );
   plif_pr = plif.getElementsByTagName('p-file-20')[0].getElementsByTagName('patron-record')[0];
   plif_pr.appendChild ( CreateElement('z303',null) );
   plif_pr.getElementsByTagName('z303')[0].appendChild (CreateElement ('z303-id',null ));
   let name_inverted = json.family_name; let name_normal = json.family_name;
   if ( typeof json.given_name === 'undefinded' ) { json.given_name=''; }
   if ( typeof json.middle_name === 'undefinded' ) { json.middle_name=''; }
   if ( json.given_name ) { 
      name_inverted = json.middle_name ? name_inverted+', '+json.given_name+' '+json.middle_name : name_inverted+', '+json.given_name;
      }
   plif_pr.getElementsByTagName('z303')[0].appendChild (CreateElement ('z303-name', name_inverted ));
   plif_pr.getElementsByTagName('z303')[0].appendChild (CreateElement ('z303-last-name', json.family_name ));
   plif_pr.getElementsByTagName('z303')[0].appendChild (CreateElement ('z303-first-name', json.given_name ));
   if ( typeof json.gender != 'undefined' ) { 
      if ( json.gender=='male' ) { plif_pr.getElementsByTagName('z303')[0].appendChild (CreateElement ('z303-gender', 'M' )); }
      else if ( json.gender=='female' ) { plif_pr.getElementsByTagName('z303')[0].appendChild (CreateElement ('z303-gender', 'F' )); }
      }
   const birth_date = json.birthdate.replace(/\-/g,'');
   plif_pr.getElementsByTagName('z303')[0].appendChild (CreateElement ('z303-birth-date', birth_date ));
   if ( json.birthplace ) {  plif_pr.getElementsByTagName('z303')[0].appendChild (CreateElement ('z303-birthplace',  json.birthplace)); }
   let title ='';
   if ( json.title_prefix ) { title += json.title_prefix ;}
   if ( json.title_suffix ) { title += ' '+json.title_suffix; }
   title = title.replace(/^\s/,'');
   if ( title ) { plif_pr.getElementsByTagName('z303')[0].appendChild (CreateElement ('z303-title', title)); }
   const email = json.email_verified ? json.email_verified : json.email;
   const phone = json.phone_number_verified ? json.phone_number_verified : json.phone_number;  
   //adres muze byt vice, je to array
   if ( typeof json.addresses==='undefined') { ExceptionError ('Data z Bankovní identity neobsahují Vaši adresu. Omlouváme se, ale nelze Vás zaregistrovat v knihovně. Využijte jinou banku pro ověření nebo nás, prosíme, navštivte osobně.','P'); return 0; }
//console.log('json.addresses.length is '+json.addresses.length);
window.debug=json;
window.debug2=json.addresses;
   if ( json.addresses.length == 0 ) { ExceptionError ('Data z Bankovní identity neobsahují Vaši adresu. Omlouváme se, ale nelze Vás zaregistrovat v knihovně. Využijte jinou banku pro ověření nebo nás, prosíme, navštivte osobně.','P'); return 0; }
   
     for ( let i=0; i<json.addresses.length; i++ ) {
//console.log('loop '+i);
      let addr_el = CreateElement('z304',null);
      let is=i.toString();
      addr_el.appendChild (CreateElement ('z304-sequence', is.padStart(2, '0') ) );
      const addr_type = json.addresses[i].type ? json.addresses[i].type : '';
//console.log('addr_type is '+addr_type);
      //poznamka k typum adres. Prevadi se typ 'PERMANENT_RESIDENCE' jako aleph typ 01 (trvala) a 'CONTACT_ADDRESS' jako aleph typ 02 (kontaktni a preferovana. Ostatni typy adres se neprevadi.
      if ( addr_type == 'SECONDARY_RESIDENCE' ) { addr_el.appendChild (CreateElement ('z304-address-type','02')); }
      else if ( addr_type == 'PERMANENT_RESIDENCE' ) { addr_el.appendChild (CreateElement ('z304-address-type','01')); }
      else { console.warn( 'data from BankId contain adrress_type '+addr_type+'. This type is not imported to Aleph.');}
      addr_el.appendChild (CreateElement ('z304-address-0', ( json.name ? json.name : json.given_name+' '+json.family_name )  ) );
      let addr_1 = json.addresses[i].street ? json.addresses[i].street : 'č.p.';
      if ( typeof json.addresses[i].streetnumber != 'undefined' ) { 
         addr_1 += ' '+ json.addresses[i].streetnumber;
         if ( typeof json.addresses[i].buildingapartment != 'undefined' ) { addr_1 += '/'+ json.addresses[i].buildingapartment ;}
         }
      else if ( typeof json.addresses[i].buildingapartment != 'undefined' ) { addr_1 += ' '+json.addresses[i].buildingapartment ; }
      //Ben 20230811 buildingapartment je číslo popisné, ne číslo bytu, výše opraveno: bereme č. popisné a orientační, na evidenční nebereme zřetel 
      //nasl. radek vklada cislo bytu, to ale v CR v adresach nepouzivame, nicmene lze pridat
      //if ( typeof json.addresses[i].buildingapartment != 'undefined' ) { addr_1 += ' ap. '+ json.addresses[i].buildingapartment; }
      addr_1=addr_1.replace(/\s+/g,' '); addr_1=addr_1.replace(/^\s/,'');
      addr_el.appendChild (CreateElement ('z304-address-1', addr_1) );
      let city = json.addresses[i].city;
      if ( typeof json.addresses[i].cityarea != 'undefined' && json.addresses[i].cityarea != json.addresses[i].city) { city += ' - '+json.addresses[i].cityarea; } //Ben 20230812
      addr_el.appendChild (CreateElement ('z304-address-2', city ) );
      if ( typeof json.addresses[i].zipcode != 'undefined' ) { addr_el.appendChild (CreateElement ('z304-zip', json.addresses[i].zipcode) ); }
      if ( typeof json.addresses[i].country != 'undefined' ) { if ( json.addresses[i].country != 'CZ' ) { 
         addr_el.appendChild (CreateElement ('z304-address-3', json.addresses[i].country) ); } }
      if ( typeof json.email != 'undefined' ) { addr_el.appendChild (CreateElement ('z304-email-address', json.email )); }
      else if ( document.querySelector('#email').value ) { if ( document.querySelector('#email').value != '' ) {
            let borMail = document.querySelector('#email').value;
//console.log('manually added mail '+borMail);
            addr_el.appendChild (CreateElement ('z304-email-address', borMail )); 
            } }

      if ( typeof json.phone_number != 'undefined' ) { addr_el.appendChild (CreateElement ('z304-telephone', json.phone_number )); }
   
//console.log('addr_el is '+addr_el);
      plif_pr.appendChild ( addr_el );
   }
   //construct xml
   let plifXml = new XMLSerializer().serializeToString(plif);
   console.log(plifXml);
   return plifXml;
   }
  
 
function CreateElement ( elName, elText ) {
   //creates and returns new element with given name and text content. If text content is empty, el. stays empty
   let el = document.createElement(elName);
   if ( elText ) {
      let elTextel = document.createTextNode(elText);
      el.appendChild(elTextel);
      }
   return el;
   } 

//show hide password
function PasswordShow() { //not in use, might be deleted
   const togglePassword = document.querySelector('#togglePassword');
   const p1=document.querySelector('input[name="password1"]'); 
   const p2=document.querySelector('input[name="password2"]');
   // toggle the type attribute
   const p1type = p1.getAttribute('type') === 'password' ? 'text' : 'password';
   p1.setAttribute('type', p1type);
   p2.disabled = p2.disabled ? false : true;
   togglePassword.classList.toggle('crossed');
   }

//after choosing a file shows button for upload to server
var zfe=document.querySelector('#ztp_file');
zfe.onchange = function() {
   if (zfe.files.length > 0) { //file choosen
      document.querySelector('#ztp_file_upload').style.display='';
      }
   }

async function getMailAleph(p) {
   //calls bankid.cgi to get patron's mail from aleph
   try {
      let resp = await fetch( backend+'?func=getmail&token='+accessToken+'&bor_id='+p );
      let respJson = await resp.json();
      if ( respJson.mail ) {
         //console.log('got email from aleph: '+respJson.mail);
         document.querySelector('#email').value = respJson.mail;
         }
      else {
         console.warn ('cgi getMail did not retun email'  );
         document.querySelector('#setMail').style.display = '';  //input pro mail, pokud ho bankid ani Aleph nema
         }
      }
   catch (error) {
      console.error('cgi getMail error - '+error);
      document.querySelector('#setMail').style.display = '';  //input pro mail, pokud ho bankid ani Aleph nema
      }
   }


async function ZtpFileUpload() {
   const ztpErrEl = ["ztp_send_error_nofile","ztp_send_error_size","ztp_send_error_type","ztp_send_error_upload"];
   ztpErrEl.forEach( i => document.querySelector('#'+i).style.display='none' );
   if (zfe.files.length == 0) { document.querySelector('#ztp_send_error_nofile').style.display=''; return 0; } 
   if (zfe.files[0].size > 2196608) { document.querySelector('#ztp_send_error_size').style.display=''; return 0; } 
   if ( ! ( zfe.files[0].type.match(/image/) || zfe.files[0].type.match(/application\/pdf/) ) ) {
      document.querySelector('#ztp_send_error_type').style.display=''; return 0; }
   let filename = accessToken.substring(0,1000) + ( zfe.files[0].name.match(/\.[^\.]+$/) ? zfe.files[0].name.match(/\.[^\.]+$/) : '');
   let formData = new FormData();
   formData.append("ztp_file",  document.querySelector('#ztp_file').files[0], filename );
   formData.append("bor_name",  document.querySelector('#login').textContent );
   window.ztp_upload='uploaded';
   try {
      let resp = await fetch( backendFileUpload, { method: "POST", cache: "no-cache", credentials: "same-origin", body: formData }  );
      let respText = await resp.text();
      if ( respText.match(/ok/) ) { 
         document.querySelector('#ztp_send_success').style.display='';
         document.querySelector('#ztp_file').style.display='none';	//ren
         document.querySelector('#ztp_file_upload').style.display='none';	//ren
         window.ztp_upload='ok';
         }
      else {
         document.querySelector('#ztp_send_error_upload').style.display='';
         window.ztp_upload='error';
         }
      }
   catch (error) {
      document.querySelector('#ztp_send_error_upload').style.display='';
      window.ztp_upload='error';
      console.error(error);
      }
   }


function ExceptionError(err,err_type) {
   //input: err - error text from script or json response
   //       err_type - E||error - chyba pri zpracovani (omlouvame se za ni a napravime)
   //                  U    - unverified (neověřeno - chybí token, v logu nic není. Neomlouvat se, měl by opakovat ověření) 
   //                  W||P - warning||problem (jina chyba, napr. neni adresa y bankid, nevalidni token apod. Neomlouvat se, ale nasmerovat ho na knihovnu)
   // TODO zapracuj err_type do procesu a neco z toho musi byt default - nejaky element co to udela.
   console.error('Error : '+err+' ERR_TYPE: '+err_type);
   if (typeof err_type == 'undefined') { var err_type='E'; }
   document.querySelector('#error_text').appendChild ( document.createTextNode('('+err+')') );	
   document.querySelector('#error').style.display='';
   document.querySelector('#patron_found').style.display='none';
   if ( err_type == 'U' ) { document.querySelector('#error_unverified').style.display=''; 
      document.querySelector('#error_error').style.display='none';}
   else if ( err_type == 'W' || err_type == 'P' ) { document.querySelector('#error_warning').style.display=''; }
   else  { document.querySelector('#error_error').style.display=''; }  //( err_type == 'error' || err_type == 'E' )

   //TODO teda jenom ve vybranych pripadehc pridat text chyby, jink by obecne error sorry mel v html byt

   }

//window.patron_found bez významu vymazat
