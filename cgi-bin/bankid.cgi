#!/exlibris/aleph/a22_1/product/bin/perl
#Backend script for bankovni identita - bankid registration
#
#returns JSON with below mentioned structure:
#
#workflow (calls):	1. func=start : iniciation, writes token to database
#                               input get, parameter: token
#				response json: '{"func": "start", "response": "ok", "text": ""}
#			2. func=check : check if person exists in Aleph (by name and birth date). Person data are written to Oracle table msvk_bankid (column patron, root element patron-record)
#			        input put, parameters: token
#			                               person - xml dle struktury aleph xserver update-bor, cf. https://developers.exlibrisgroup.com/aleph/apis/aleph-x-services/update_bor/
#				json responses - registration valid - platna registrace (patron exists and has valid registration):
#					{"func": "check", response": "registration_valid", "text": "{{expiration_date_YYYYMMDD}}.'", "daysbefore": "{{days_before_expiry}}"}
#					      - found in Aleph -nasel se v Alephu (person with the  same name and birth date found among patrons in Aleph) :
#					{"func": "check", "response": "found", "bor_id": "{{bor_id}}", "bor_login": "{{bor_login}}", "bor_status": "{{bor_status}}", "bor_status_name": "{{bor_status_name}}", "registration_fee": {{registration_fee}}"};
#					      - New person/patron - novy ctenar:
#					{"func": "check", response": "new", "bor_login": "{{bor_login}}", "bor_status": "...", "bor_status_name": "...", "registration_fee": "..."}
#					      - Patron is under set minimal age ($patron_minimal_age), cannot be registrated - ma pod stanoveny vek ($patron_minimal_age), nelze registrovat:
#					{"func": "check", response": "too young", "age_limit": "{{limit}}"}
#			3. func=registrate : after confirming the registration in frontend. Make the registration, incl. cash and log. Confirm it.
#			        input put, parameters: token, password (set by user in WUI frontend)
#			        json response: {"func": "registrate", "response": "ok"}
#			4. func=getmail : returns person e-mail from Aleph - vrati mail ctenare z alephu, pokud ho nema v datech bankid
#			        input get, parameters: token, bor_id
#			        json response {"func": "get_mail", "mail": {{mail}}}         
#    error response: { "response": "error", "text": "{{error_text}}", "level": "'error'||..." }
#
#Requirememns: Perl with modules: Encode, utf8, LWP, DBI, CGI, XML::Simple, URI::Escape, POSIX, Date::Parse, Data::Dumper;

#	In Oracle, user $adm_base must exist msvk_bankid table with structure:
#		create table msvk_bankid ( timestamp date, token varchar2(2000), bor_id varchar2(12), bor_login varchar2(20), bor_status char(2), registration_fee varchar2(22), fee_type char(4),  patron varchar2(4000), new_patron char(1) );
#		--with recommended indexes:
#		create index ind_token on msvk_bankid (token);
#		create index ind_timestamp on msvk_bankid (timestamp);	
#		create index ind_bor_login on msvk_bankid (bor_login);
#
#Made by Matyas Bajger & Renata Benesova, 2023 for Moravian-Silesian Research Library in Ostrava https://www.msvk.cz
#License CC BY NC 4.0		
#
use strict;
use warnings;
use File::Basename; #mat20231022
use lib dirname (__FILE__); #mat20231022
use Encode qw(decode encode);
use utf8;
binmode STDIN, ":encoding(UTF-8)";
binmode STDOUT, ":encoding(UTF-8)";
binmode *STDOUT, ':encoding(UTF-8)';
use LWP;
use DBI;
use CGI ':utf8';
use XML::Simple qw(:strict);
use URI::Escape;
use POSIX qw/strftime/;
use Date::Parse;
use Data::Dumper;
$ENV{NLS_LANG} = 'AMERICAN_AMERICA.AL32UTF8';
#local $/=undef;

#load external config, Mat20231022
our ($address_valid_days, $adm_base, $admin_mail, $aleph_version, $cash_description, $circ_log_action, $circ_log_text, $days_before_expiry, $mail2patron_url, $patron_bor_status_default, $patron_bor_type, $patron_export_consent, $patron_home_library, $patron_ill_active_limit, $patron_ill_library, $patron_ill_total_limit, $patron_language, $patron_login_id_type, $patron_login_prefix, $patron_minimal_age, $patron_online_note, $patron_plain_html, $patron_send_all_letters, $sid, $tab18_file, $tab31_file, $tab_pc_tab_exp_field_extended, $xserver_upd_bor_password, $xserver_upd_bor_user, $xserver_url, $ztp_file_directory, $ztp_registrace_mail, $check_patron_ignore_dia, $child_max_age, $child_bor_type, $retired_min_age,$retired_bor_type, $bor_status_preregistrated, $retired_max_age, @current_bor_status_preserve, $child_bor_status, $youth_max_age, $youth_bor_status, $retired_bor_status);
require 'bankid.config';


###########################################################################################


#get request from opac and call appropriate sub
my $comm_in = CGI->new;
my $remote_host = $comm_in->remote_host();
my $remote_addr = $comm_in->remote_addr();
my $timestamp = strftime "%Y%m%d-%H:%M:%S", localtime;
my $today = strftime "%Y%m%d", localtime;
my $adm_base_upper = uc($adm_base);
open ( LOGFILE, ">>bankid.log" );
binmode LOGFILE, ":encoding(UTF-8)";

my $dbh = DBI->connect($sid, $adm_base, $adm_base, {AutoCommit => 1}) or run_exemption ("couldn't connect to database - ".$DBI::errstr, 'error');

my $comm_out = CGI->new;
print $comm_out->header(-type => "application/json", -charset => "UTF-8");
unless ( $comm_in->param('token') ) { run_exemption ('URL parameter token is missing.','error'); }
my $token = $comm_in->param('token');
unless ( $comm_in->param('func') ) { run_exemption ('URL parameter func is missing.','error'); }
my $func = $comm_in->param('func');
if ( $func eq 'start' ) { writeToken(); }
elsif ( $func eq 'check' ) { checkPatron(); }
elsif ( $func eq 'registrate' ) { registratePatron(); }
elsif ( $func eq 'getmail' ) { getMail(); }
else { run_exemption ("URL parameter func has unrecognised value: $func",'error'); }



sub writeToken {
   #after first step of bankid authentication, token is written to db. This token is required and check in following calls of the session (check, registrate)
   print LOGFILE "$timestamp writeToken $remote_addr\n";
   unless ( $comm_in->param('token') ) { run_exemption ('Token parameter is missing','error'); }
   my $token=$comm_in->param('token') ;
   print LOGFILE "	token: $token\n";
   #write token to DB 
   my $sth = $dbh->prepare("insert into msvk_bankid ( timestamp, token ) values ( to_date('$timestamp','YYYYMMDD-HH24:MI:SS'), '$token')");
   $sth->execute or run_exemption ("Error inserting new token/session to database: ".$DBI::errstr, 'error');
   $sth->finish();
   #delete old rows from oracle table
   my $sth2 = $dbh->prepare("delete from msvk_bankid where timestamp<sysdate-7");
   $sth2->execute or run_exemption ("Error while deleting old rows in tab msvk_bankid: ".$DBI::errstr, 'warning');
   $sth2->finish();
   print LOGFILE "      token written to DB\n\n";
   print '{"func": "start", "response": "ok", "text": ""}'."\n";;
   close ( LOGFILE );
   $dbh->disconnect;
   return 1;
   }

sub checkPatron {
   #checks input person Data from BankId. Checks if patron does not exists in Aleph data already.
   print LOGFILE "$timestamp checkPatron $remote_addr - token $token\n";
   my $token=$comm_in->param('token') ;
   checkToken($token);

   #check and get  parameters
   unless ( $comm_in->param('patron') ) { run_exemption('Post parameter "patron" is missing','error'); }
   my $borBtop = XMLin( $comm_in->param('patron') , ForceArray => 0, KeyAttr => {} ); #patron data from BankId
   my $borB = $borBtop->{'patron-record'};
   unless ( $borB->{z303}->{'z303-last-name'} ) { run_exemption('Post parameter "patron" does not contain element "z303/z303-last-name".','error'); }
   unless ( $borB->{z303}->{'z303-first-name'} ) { run_exemption('Post parameter "patron" does not contain element "z303/z303-first-name".','error'); }
   unless ( $borB->{z303}->{'z303-birth-date'} ) { run_exemption('Post parameter "patron" does not contain element "z303/z303-birth-date".','error'); }
   $borB->{z303}->{'z303-birth-date'} =~ s/\s//g;
   unless ( $borB->{z303}->{'z303-birth-date'} =~ /^[1-2][0-9]{3}[0-1][0-9][0-3][0-9]$/ ) { run_exemption ("Warning - patron birthdate '".$borB->{'birth-date'}."' does not look to be valid or in format YYYYMMDD",'warning'); }
   print LOGFILE "	last-name: ".$borB->{z303}->{'z303-last-name'}." ; first-name: ".$borB->{z303}->{'z303-first-name'}." ; birthdate: ".$borB->{z303}->{'z303-birth-date'}."\n";
   
   #check patron age
   my $bor_age = age($borB->{z303}->{'z303-birth-date'});
   if ($patron_minimal_age) {
      if ( $bor_age < $patron_minimal_age ) { 
         print LOGFILE "Patron age $bor_age is under minimal limit $patron_minimal_age . END\n";
         print '{"func": "check", "response": "too young", "age_limit": "'.$patron_minimal_age.'"}'."\n";
         close ( LOGFILE );
         $dbh->disconnect;
         return 1;
         }
      }
      
   #check patron in aleph database
   my $sth;
   if ($check_patron_ignore_dia) { #ignore diacritics
      $sth = $dbh->prepare("select z303_rec_key, z303_last_name, z303_first_name, Z303_BIRTH_DATE, Z305_BOR_STATUS, Z305_EXPIRY_DATE, z308_rec_key from z303, z305, z308 where z303_rec_key=substr(z305_rec_key,1,12) and z303_rec_key=z308_id and Z303_BIRTH_DATE='".$borB->{z303}->{'z303-birth-date'}."' and upper(z303_LAST_NAME)=upper('".$borB->{z303}->{'z303-last-name'}."') and upper(z303_FIRST_NAME)=upper('".$borB->{z303}->{'z303-first-name'}."') and z308_rec_key like '".$patron_login_id_type."%'");
      }
   else {   
      $sth = $dbh->prepare("select z303_rec_key, z303_last_name, z303_first_name, Z303_BIRTH_DATE, Z305_BOR_STATUS, Z305_EXPIRY_DATE, z308_rec_key from z303, z305, z308 where z303_rec_key=substr(z305_rec_key,1,12) and z303_rec_key=z308_id and Z303_BIRTH_DATE='".$borB->{z303}->{'z303-birth-date'}."' and upper(NLSSORT(z303_LAST_NAME,'NLS_SORT=BINARY_AI'))=upper(NLSSORT('".$borB->{z303}->{'z303-last-name'}."','NLS_SORT=BINARY_AI')) and upper(NLSSORT(z303_FIRST_NAME,'NLS_SORT=BINARY_AI'))=upper(NLSSORT('".$borB->{z303}->{'z303-first-name'}."','NLS_SORT=BINARY_AI')) and z308_rec_key like '".$patron_login_id_type."%'");
      }    
   $sth->execute or run_exemption ("Error selecting in database while try to checkPatron: ".$DBI::errstr, 'error');
   my $row = $sth->fetchrow_hashref;
   my $bor_login=''; my $bor_id = ''; my $new_patron = '';
   #get patron status and registration fee and write them to msvk_bankid ora table
   my ($bor_status, $bor_status_name) = getPatronStatus($bor_age, $row->{Z305_BOR_STATUS});
   unless ( $bor_status ) { run_exemption ("Error - patron status was not recognised",'error'); }
   my ($fee_check, $fee_type)  = getRegistrationFee ( $bor_status, $row );
   unless ( $fee_check ) { run_exemption ("Error - registration fee was not recognised",'error'); }
   
   #generate login BEN 
   #get max current login, both from z308 and msvk_bankid tables (due to potential unfinished processed not written to z308 (yet))
   my $patron_login_prefix_length4z308 = length($patron_login_prefix)+1+2;
   my $patron_login_prefix_length4msvk_bankid = length($patron_login_prefix)+1;
   my $new_bor_login = '';
   my $sth_login = $dbh->prepare("select max(login_seq) max_login_seq from (select max(substr(z308_rec_key,$patron_login_prefix_length4z308)) login_seq from z308 where z308_rec_key like '".$patron_login_id_type.$patron_login_prefix."%' union select max(substr(bor_login,$patron_login_prefix_length4msvk_bankid)) login_seq from msvk_bankid where bor_login like '".$patron_login_prefix."%')");
   $sth_login->execute or run_exemption ("Error selecting in database while try to get last login sequence: ".$DBI::errstr, 'error');
   my $row_login = $sth_login->fetchrow_hashref;
   if ( $row_login ) {
       my $card_seq = $row_login->{'MAX_LOGIN_SEQ'}; $card_seq =~ s/\s+//g;
       unless ( $card_seq =~ /^[0-9]+$/ ) { run_exemption("Error card sequence used in aleph is not a number  (with prefix $patron_login_prefix",'error'); }
       $card_seq++;
       $new_bor_login = $patron_login_prefix.$card_seq;
         }
   else { #no previous login found
       $new_bor_login = $patron_login_prefix.'00000001';      
         }
   # generate login END
     
   if ( $row->{Z303_REC_KEY} ) { #patron has been found in the aleph database
      print LOGFILE "	patron has been found in Aleph with ID: ".$row->{'Z303_REC_KEY'}."\n";

      #check valid registration including no. days before expiring the registration, when registration renew is allowed
      #this check is ommitted if patron has preregistrated borrower status
      my $expiry_limit = strftime('%Y%m%d', localtime(time + $days_before_expiry * 86400));
      if ( $row->{Z305_EXPIRY_DATE} > $expiry_limit and $row->{Z305_BOR_STATUS} ne $bor_status_preregistrated ) { 
         print LOGFILE "      NOTE patron has valid registration till ".$row->{Z305_EXPIRY_DATE}.", renewal can be done not more than $days_before_expiry days before this date\nEND\n\n";
         print '{"func": "check", "response": "registration_valid", "text": "'.$row->{Z305_EXPIRY_DATE}.'", "daysbefore": "'.$days_before_expiry.'"}'."\n";
         close ( LOGFILE );
         $dbh->disconnect;
         return 1;
         }
      $bor_id = $row->{Z303_REC_KEY};
      $bor_login = substr($row->{Z308_REC_KEY}, 2); $bor_login =~ s/\s//g;

      if ( $bor_status_preregistrated ) { 
         if ( $bor_status eq $bor_status_preregistrated ) {
            $bor_login = $new_bor_login;  #BEN preregistrated patrons got new login, although they got a login on preregistration
            }
         }   

      #MSVK specifikum
      #if ( $bor_login =~ /^B/ ) { $bor_login = $new_bor_login; } ##BEN historicky vzdálenì registrovaní login B% zmìnit na E%, na statusu nezáleží
      #MSVK specifikum END 
      
      #write patron data to msvk_bankid table
      if ( $row->{Z305_BOR_STATUS} eq $bor_status_preregistrated ) { $new_patron = 'B'; } #preregistrated gets extra sign, as their bloks (used in preregistration) are cleared
	  else { $new_patron = 'N'; }
      my $sth0= $dbh->prepare("update msvk_bankid set patron='".$comm_in->param('patron')."', bor_id='$bor_id', bor_login='$bor_login', bor_status='$bor_status', registration_fee='$fee_check', fee_type='$fee_type', new_patron='$new_patron' where token='$token'");
      $sth0->execute or run_exemption ("Error updating database while try to add patron data to msvk_bankid: ".$DBI::errstr, 'error');
      $sth0->finish();
      print LOGFILE "	patron has been found in Aleph with id: $bor_id, and login: $bor_login\n";
      print '{"func": "check", "response": "found", "bor_id": "'.$bor_id.'", "bor_login": "'.$bor_login.'", "bor_status": "'.$bor_status.'", "bor_status_name": "'.$bor_status_name.'", "registration_fee": "'.$fee_check.'"}';
      close ( LOGFILE );
      $dbh->disconnect;
      return 1;
      }
      
   else { #patron has NOT been found in the aleph database
      print LOGFILE "      new patron\n";
	  $bor_login = $new_bor_login;  #BEN 
      #write patron data to msvk_bankid table
      my $sth0= $dbh->prepare("update msvk_bankid set patron='".$comm_in->param('patron')."', bor_id='$bor_id', bor_login='$bor_login', bor_status='$bor_status', registration_fee='$fee_check', fee_type='$fee_type', new_patron='Y' where token='$token'");
      $sth0->execute or run_exemption ("Error updating database while try to add patron data to msvk_bankid: ".$DBI::errstr, 'error');
      $sth0->finish();
      print LOGFILE "	new patron, got login: $bor_login\n";
      print '{"func": "check", "response": "new", "bor_login": "'.$bor_login.'", "bor_status": "'.$bor_status.'", "bor_status_name": "'.$bor_status_name.'", "registration_fee": "'.$fee_check.'"}'."\n";
      close ( LOGFILE );
      $sth_login->finish();
      $dbh->disconnect;
      return 1;
      }

   } #sub checkPatron END


sub registratePatron {
#checks patron data in msvk_bankid table written there before. Prepares person data to PLIF xml format and puts them to Aleph Rest-api. 
#using DB update creates new fee for registration and writes new circulation log (z309) event on registration
   print LOGFILE "$timestamp registratePatron $remote_addr\n";
   my $token=$comm_in->param('token') ;
   checkToken($token);

   unless ( $comm_in->param('password') ) { run_exemption ('URL parameter password is missing.','error'); }
   my $bor_password = $comm_in->param('password') ? $comm_in->param('password') : '';

   #get data from database msvk_bankid
   my $sth = $dbh->prepare("select bor_id, bor_login, bor_status, registration_fee, fee_type, patron, new_patron from msvk_bankid where token='".$token."'");
   $sth->execute or run_exemption ('Error selecting in database while try get data from msvk_bankid: '.$DBI::errstr, 'error');
   my $row = $sth->fetchrow_hashref;
   unless ($row) { run_exemption ("Patron has not been found in registration table msvk_bankid",'error'); }

   my $bor_login = $row->{BOR_LOGIN};
   my $bor_id = $row->{BOR_ID};
   my $bor_status = $row->{BOR_STATUS};
   my $registration_fee = $row->{REGISTRATION_FEE};
   my $fee_type = $row->{FEE_TYPE};
   my $bor_data = $row->{PATRON};
   unless ( $bor_data ) { run_exemption ("Patron id has been found in registration table msvk_bankid, but row contains no patron xml data",'error'); }
   my $bor_datax = XMLin($bor_data, ForceArray => 0, KeyAttr => {} );

   #borrower type on base on their age,  mat20231022
   my $bor_age = age($bor_datax->{'patron-record'}->{z303}->{'z303-birth-date'});
   if ($child_max_age and $child_bor_type) { 
      if ( $bor_age <= $child_max_age ) { $patron_bor_type = $child_bor_type; }  
      } 
   if ($retired_max_age and $retired_bor_type) { 
      if ( $bor_age >= $retired_min_age ) { $patron_bor_type = $retired_bor_type; }  
      } 

   #default values for PLIF xml - doplneni defaultnich hodnot 
   delete $bor_datax->{'xmlns'};
   $bor_datax->{'patron-record'}->{z303}->{'z303-con-lng'} = $patron_language;
   #$bor_datax->{'patron-record'}->{z303}->{'z303-delinq-1'} = '00';
   #$bor_datax->{'patron-record'}->{z303}->{'z303-delinq-2'} = '00';
   #$bor_datax->{'patron-record'}->{z303}->{'z303-delinq-3'} = '00';
   $bor_datax->{'patron-record'}->{z303}->{'z303-ill-library'} =  $patron_ill_library;
   $bor_datax->{'patron-record'}->{z303}->{'z303-home-library'} =  $patron_home_library;
   $bor_datax->{'patron-record'}->{z303}->{'z303-ill-total-limit'} = $patron_ill_total_limit;
   $bor_datax->{'patron-record'}->{z303}->{'z303-ill-active-limit'} = $patron_ill_active_limit;
   $bor_datax->{'patron-record'}->{z303}->{'z303-export-consent'} = $patron_export_consent;
   $bor_datax->{'patron-record'}->{z303}->{'z303-send-all-letters'} = $patron_send_all_letters;
   $bor_datax->{'patron-record'}->{z303}->{'z303-plain-html'} = $patron_plain_html;
   if ( ref($bor_datax->{'patron-record'}->{z304}) eq 'ARRAY' ) {
      if (  $bor_datax->{'patron-record'}->{z304}[0] ) { 
         $bor_datax->{'patron-record'}->{z304}[0]->{'z304-date-from'} = $today; 
         $bor_datax->{'patron-record'}->{z304}[0]->{'z304-date-to'} = strftime "%Y%m%d", localtime(str2time($today) + ($address_valid_days * 24 * 60 * 60));
		 if ( $comm_in->param('email') ) { $bor_datax->{'patron-record'}->{z304}[0]->{'z304-email-address'} =  $comm_in->param('email'); }
         }
      if (  $bor_datax->{'patron-record'}->{z304}[1] ) { 
         $bor_datax->{'patron-record'}->{z304}[1]->{'z304-date-from'} = $today; 
         $bor_datax->{'patron-record'}->{z304}[1]->{'z304-date-to'} = strftime "%Y%m%d", localtime(str2time($today) + ($address_valid_days * 24 * 60 * 60));
		 if ( $comm_in->param('email') ) { $bor_datax->{'patron-record'}->{z304}[1]->{'z304-email-address'} =  $comm_in->param('email'); }
         }
      if (  $bor_datax->{'patron-record'}->{z304}[2] ) { 
         $bor_datax->{'patron-record'}->{z304}[2]->{'z304-date-from'} = $today; 
         $bor_datax->{'patron-record'}->{z304}[2]->{'z304-date-to'} = strftime "%Y%m%d", localtime(str2time($today) + ($address_valid_days * 24 * 60 * 60));
		 if ( $comm_in->param('email') ) { $bor_datax->{'patron-record'}->{z304}[2]->{'z304-email-address'} =  $comm_in->param('email'); }
         }
      }
   else { 
      $bor_datax->{'patron-record'}->{z304}->{'z304-date-from'} = $today; 
      $bor_datax->{'patron-record'}->{z304}->{'z304-date-to'} = strftime "%Y%m%d", localtime(str2time($today) + ($address_valid_days * 24 * 60 * 60));
	  if ( $comm_in->param('email') ) { $bor_datax->{'patron-record'}->{z304}->{'z304-email-address'} =  $comm_in->param('email'); }
      }
   #registrace
   $bor_datax->{'patron-record'}->{z305}->{'z305-sub-library'}=uc($adm_base);
   $bor_datax->{'patron-record'}->{z305}->{'z305-bor-type'}=$patron_bor_type;
   $bor_datax->{'patron-record'}->{z305}->{'z305-bor-status'}=$bor_status;
   $bor_datax->{'patron-record'}->{z305}->{'z305-registration-date'}=$today;
   $bor_datax->{'patron-record'}->{z305}->{'z305-note'}='';

   #check and process ztp or other card photo
   # If registrating person has a card for extra priviledges (status) in the library, like for impaired (ZTP), they can upload it (photo or scan) in registration form (frontend).
   #  The picture is send to the email of registration department, where it is manually checked and processed.
   if ( $comm_in->param('ztp_file') ) {
      my $ztp_filename = $comm_in->param('ztp_file');
      $ztp_filename =~ s/.*[\/\\](.*)/$1/;
      $ztp_filename = $bor_id."_".$ztp_filename;
      print LOGFILE "Card for extra priviledgies, like impaired (ZTP etc.) has been uploaded to : $ztp_filename\n";
      my $upload_filehandle = $comm_in->upload('ztp_file');
      if ( !$upload_filehandle && $comm_in->cgi_error ) { run_exemption ("Error uploading file $ztp_filename with document for free registration : ".$comm_in->cgi_error,'error'); }
      open UPLOADFILE, ">:raw", "$ztp_file_directory/$ztp_filename";
      binmode UPLOADFILE;
      while ( <$upload_filehandle> )  { print UPLOADFILE; }
      close UPLOADFILE;
      #send file by mail to library
      open(FILE, "<:raw", "$ztp_file_directory/$ztp_filename");
      binmode FILE;
      my $content=<FILE>;
      close(FILE);
      print LOGFILE "Card for extra priviledgies, like impaired (ZTP etc.) has been is to be sent to : $ztp_registrace_mail\n";
      open(MAIL, "|/usr/sbin/sendmail -t");
      print MAIL <<"EOF";
From: aleph\@svkos.cz
To: $ztp_registrace_mail
Subject: Online registrace - ID $bor_id - prukaz k zdarma registraci
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="----=_NextPart_000_002F_01C3F989.5E1B7780"


------=_NextPart_001_0030_01C3F989.5E1B7780
Content-Type: text/plain;
Content-Transfer-Encoding: quoted-printable

Ctenar s ID $bor_id se online registroval pomoci BankID a posila prukaz k bezplatne registraci

below is the binary content of a jpg in a new multipart sectiondd

------=_NextPart_000_002F_01C3F989.5E1B7780
Content-Type: text/plain; name="$ztp_filename"
Content-Disposition: attachment; filename="$ztp_filename"
Content-Transfer-Encoding: base64

$content

------=_NextPart_000_002F_01C3F989.5E1B7780--
EOF
      close(MAIL);
      }

   #get patron rights from tab table
   my $patron_status_found=0;
   open(my $fh31, '<', $tab31_file) or run_exemption ("Cannot open tab31 file with patron definitions - $tab31_file",'error');
   while (my $row31 = <$fh31>) {
     chomp $row31;
     if ( $row31 =~ /^\s*\!/ ) { next; } #skip comments
     if ( substr($row31,6,2) eq $bor_datax->{'patron-record'}->{z305}->{'z305-bor-status'} ) { 
        $patron_status_found=1;
        $bor_datax->{'patron-record'}->{z305}->{'z305-loan-permission'} = substr($row31,9,1);
        $bor_datax->{'patron-record'}->{z305}->{'z305-photo-permission'} = substr($row31,11,1);
        $bor_datax->{'patron-record'}->{z305}->{'z305-over-permission'} = substr($row31,13,1);
        $bor_datax->{'patron-record'}->{z305}->{'z305-multi-hold'} = substr($row31,15,1);
        $bor_datax->{'patron-record'}->{z305}->{'z305-loan-check'} = substr($row31,17,1);
        $bor_datax->{'patron-record'}->{z305}->{'z305-hold-permission'} = substr($row31,19,1);
        $bor_datax->{'patron-record'}->{z305}->{'z305-renew-permission'} = substr($row31,21,1);
        $bor_datax->{'patron-record'}->{z305}->{'z305-rr-permission'} = substr($row31,55,1);
        $bor_datax->{'patron-record'}->{z305}->{'z305-ignore-late-return'} = substr($row31,23,1);
        $bor_datax->{'patron-record'}->{z305}->{'z305-photo-charge'} = substr($row31,25,1);
        #get and count expiry date (registration)
        my $expiry_operator  = substr($row31,27,1); # + = add to current date, A = actual date;
        my $expiry_type_operator  = substr($row31,29,1); #D=day M=month Y=year;
        my $expiry  = substr($row31,31,8);
        if ( $expiry_operator eq 'A' ) { 
           $bor_datax->{'patron-record'}->{z305}->{'z305-expiry-date'} = $expiry;
           }
        else {
           $expiry =~ s/^\s+//g;
           #recount to days
           if ( $expiry_type_operator eq 'M' ) { $expiry = $expiry * 31; }
           elsif ( $expiry_type_operator eq 'Y' ) { $expiry = $expiry * 365; }
           $bor_datax->{'patron-record'}->{z305}->{'z305-expiry-date'} = strftime('%Y%m%d', localtime(time + $expiry * 86400));
           }
        $bor_datax->{'patron-record'}->{z305}->{'z305-hold-on-shelf'} = substr($row31,51,1);
        $bor_datax->{'patron-record'}->{z305}->{'z305-booking-permission'} = substr($row31,60,1);
        $bor_datax->{'patron-record'}->{z305}->{'z305-booking-ignore-hours'} = substr($row31,62,1);
        last;
        }
      }
   close ($fh31);
   unless ($patron_status_found) { run_exemption ("Patron status '".$bor_datax->{'patron-record'}->{z305}->{'z305-bor-status'}."' not found in tab31 file $tab31_file",'error'); };
   
   
   $bor_datax->{'patron-record'}->{z305}->{'z305-last-activity-date'} = '00000000';
   #$bor_datax->{'patron-record'}->{z305}->{'z305-delinq-1'} = '00';
   #$bor_datax->{'patron-record'}->{z305}->{'delinq-n-1'} = '00000000';
   #$bor_datax->{'patron-record'}->{z305}->{'delinq-1-update-date'} = '00000000';
   #$bor_datax->{'patron-record'}->{z305}->{'delinq-1-cat-name'} = '';
   #$bor_datax->{'patron-record'}->{z305}->{'z305-delinq-2'} = '00';
   #$bor_datax->{'patron-record'}->{z305}->{'delinq-n-2'} = '00000000';
   #$bor_datax->{'patron-record'}->{z305}->{'delinq-2-update-date'} = '00000000';
   #$bor_datax->{'patron-record'}->{z305}->{'delinq-2-cat-name'} = '';
   #$bor_datax->{'patron-record'}->{z305}->{'z305-delinq-3'} = '00';
   #$bor_datax->{'patron-record'}->{z305}->{'delinq-n-3'} = '00000000';
   #$bor_datax->{'patron-record'}->{z305}->{'delinq-3-update-date'} = '00000000';
   #$bor_datax->{'patron-record'}->{z305}->{'delinq-3-cat-name'} = '';
   
   #set note to new and preregistrated patrons - novemu a prederegistrovanemu dej poznamku
   if ( $row->{NEW_PATRON} eq 'Y' || $row->{NEW_PATRON} eq 'B') {
	$bor_datax->{'patron-record'}->{z303}->{'z303-field-1'} = $patron_online_note ? $patron_online_note : '';
    }
   #$bor_datax->{'patron-record'}->{z303}->{'z303-field-2'} = '';
   #$bor_datax->{'patron-record'}->{z303}->{'z303-field-3'} = '';
   #$bor_datax->{'patron-record'}->{z305}->{'z305-end-block-date'} = '00000000';
   
   #login
   $bor_datax->{'patron-record'}->{z308}->{'z308-key-type'} = $patron_login_id_type;
   $bor_datax->{'patron-record'}->{z308}->{'z308-key-data'} = $bor_login;
   $bor_datax->{'patron-record'}->{z308}->{'z308-user-library'} = '';
   $bor_datax->{'patron-record'}->{z308}->{'z308-verification'} = $bor_password;
   $bor_datax->{'patron-record'}->{z308}->{'z308-verification-type'} = '00';
   $bor_datax->{'patron-record'}->{z308}->{'z308-status'} = 'AC';
   $bor_datax->{'patron-record'}->{z308}->{'z308-encryption'} = 'N';

   #write patron data to API
   if ( $row->{NEW_PATRON} eq 'N' || $row->{NEW_PATRON} eq 'B' ) {  
      #patron already exists, update her/his data and registrate
      $bor_datax->{'patron-record'}->{z303}->{'record-action'} = 'A';
      $bor_datax->{'patron-record'}->{z303}->{'match-id-type'} = '00';
      $bor_datax->{'patron-record'}->{z303}->{'match-id'} = $bor_id;
      $bor_datax->{'patron-record'}->{z303}->{'z303-id'} = $bor_id;
	  #if patron has been pre-registrated, clear their blocks 
	  if ( $row->{NEW_PATRON} eq 'B' ) { 
	     $bor_datax->{'patron-record'}->{z303}->{'z303-delinq-1'} = '00'; 
		 $bor_datax->{'patron-record'}->{z303}->{'z303-delinq-n-1'} = '';
         $bor_datax->{'patron-record'}->{z303}->{'z303-delinq-2'} = '00'; 
		 $bor_datax->{'patron-record'}->{z303}->{'z303-delinq-n-2'} = '';
	     $bor_datax->{'patron-record'}->{z303}->{'z303-delinq-3'} = '00'; 
		 $bor_datax->{'patron-record'}->{z303}->{'z303-delinq-n-3'} = '';
		 }
      if ( ref($bor_datax->{'patron-record'}->{z304}) eq 'ARRAY' ) {
         $bor_datax->{'patron-record'}->{z304}[0]->{'record-action'} = 'A';
         $bor_datax->{'patron-record'}->{z304}[0]->{'z304-id'} = $bor_id;
         if (  $bor_datax->{'patron-record'}->{z304}[1] ) {
            $bor_datax->{'patron-record'}->{z304}[1]->{'record-action'} = 'A';
            $bor_datax->{'patron-record'}->{z304}[1]->{'z304-id'} = $bor_id;
            }
         if (  $bor_datax->{'patron-record'}->{z304}[2] ) {
            $bor_datax->{'patron-record'}->{z304}[2]->{'record-action'} = 'A';
            $bor_datax->{'patron-record'}->{z304}[2]->{'z304-id'} = $bor_id;
            }
         }
      else {
         $bor_datax->{'patron-record'}->{z304}->{'record-action'} = 'A';
         $bor_datax->{'patron-record'}->{z304}->{'z304-id'} = $bor_id;
         }
      $bor_datax->{'patron-record'}->{z305}->{'record-action'} = 'A';
      $bor_datax->{'patron-record'}->{z305}->{'z305-id'} = $bor_id;
      $bor_datax->{'patron-record'}->{z308}->{'record-action'} = 'A';
      $bor_datax->{'patron-record'}->{z308}->{'z308-id'} = $bor_id;
      }
   else { #new patron, add data
      $bor_datax->{'patron-record'}->{z303}->{'record-action'} = 'A';
      $bor_datax->{'patron-record'}->{z303}->{'match-id-type'} = '00';
      $bor_datax->{'patron-record'}->{z303}->{'match-id'} = '';
      if ( ref($bor_datax->{'patron-record'}->{z304}) eq 'ARRAY' ) {
         $bor_datax->{'patron-record'}->{z304}[0]->{'record-action'} = 'A';
         if (  $bor_datax->{'patron-record'}->{z304}[1] ) { $bor_datax->{'patron-record'}->{z304}[1]->{'record-action'} = 'A'; }
         if (  $bor_datax->{'patron-record'}->{z304}[2] ) { $bor_datax->{'patron-record'}->{z304}[2]->{'record-action'} = 'A'; }
         }
      else { $bor_datax->{'patron-record'}->{z304}->{'record-action'} = 'A'; }
 
      $bor_datax->{'patron-record'}->{z305}->{'record-action'} = 'A';
      $bor_datax->{'patron-record'}->{z308}->{'record-action'} = 'A';
      }
   #$bor_data=XMLout($bor_datax, RootName => 'p-file-20',  KeyAttr => [ ] );
   $bor_data=XMLout($bor_datax, RootName => 'p-file-20', NoAttr => 1 ,  KeyAttr => [ ]);
   my $ua = LWP::UserAgent->new;
   $ua->timeout(10);
   my $ua_response = $ua->post( $xserver_url, {op=> 'update-bor', library => $adm_base_upper, user_name => $xserver_upd_bor_user, user_password => $xserver_upd_bor_password, update_flag => 'Y', xml_full_req => $bor_data} ); 
   unless ( $ua_response->is_success() ) {  run_exemption ("Error calling x-server for insert/update patron. Call $xserver_url  -- returns ".$ua_response->status_line()."\n",'error');}
   my $new_patron_response = $ua_response->decoded_content();
print LOGFILE "DEBUG response $new_patron_response\n\n\n";
   my $new_patron_responseX = XMLin( $new_patron_response, ForceArray => 1, KeyAttr => {} );
   foreach my $response_error ( @{ $new_patron_responseX->{'error'} } ) {
      unless ( $response_error =~ /Succeeded/ ) { 
         my $err_text='';
         foreach my $err_texti ( @{ $new_patron_responseX->{'error'} } ) { $err_text=$err_text.$err_texti ;}  
         run_exemption ("Error while inserting new patron - Xserver API returns : $err_text",'error'); 
         }
      }
   if ( $new_patron_responseX->{'patron-id'}[0] ) { $bor_id = $new_patron_responseX->{'patron-id'}[0]; }
   print LOGFILE "	patron xml data written to aleph\n";
   
   #write fee to z31 table (Aleph API for writing cash not found)
   my @ctime = localtime();
   my $secs_since_midnight = ($ctime[2] * 3600) + ($ctime[1] * 60) + $ctime[0];
   $secs_since_midnight = LPad($secs_since_midnight,7,'0');
   my $z31_rec_key = RPad($bor_id,12,' ').$today.$secs_since_midnight;

   my $z31_sum = LPad($registration_fee, 14, '0');
   my $z31_payment_date_key = strftime "%Y%m%d%H%M", localtime;
   my $z31_update_time_stamp = strftime "%Y%m%d%H%M%S", localtime; $z31_update_time_stamp = RPad($z31_update_time_stamp,15,'0');
   my $sth_fee = $dbh->prepare("insert into z31 (  Z31_REC_KEY, Z31_DATE_X, Z31_STATUS, Z31_SUB_LIBRARY, Z31_ALPHA, Z31_TYPE, Z31_CREDIT_DEBIT, Z31_SUM, Z31_VAT_SUM, Z31_NET_SUM, Z31_PAYMENT_DATE_KEY, Z31_PAYMENT_CATALOGER, Z31_PAYMENT_TARGET, Z31_PAYMENT_IP, Z31_PAYMENT_RECEIPT_NUMBER, Z31_PAYMENT_MODE, Z31_PAYMENT_IDENTIFIER, Z31_DESCRIPTION, Z31_KEY, Z31_KEY_TYPE, Z31_TRANSFER_DEPARTMENT, Z31_TRANSFER_DATE, Z31_TRANSFER_NUMBER, Z31_RECALL_TRANSFER_STATUS, Z31_RECALL_TRANSFER_DATE, Z31_RECALL_TRANSFER_NUMBER, Z31_RELATED_Z31_KEY, Z31_RELATED_Z31_KEY_TYPE, Z31_REQUESTER_NAME, Z31_UPD_TIME_STAMP, Z31_PAYMENT_IP_V6, Z31_NOTE ) values ( 
   '$z31_rec_key', --Z31_REC_KEY
   '$today', --Z31_DATE_X
   'O', --Z31_STATUS
   '$adm_base_upper', --Z31_SUB_LIBRARY
   'L', --Z31_ALPHA
   $fee_type, --Z31_TYPE - NUMBER(4)
   'D', --Z31_CREDIT_DEBIT
   '$z31_sum', --Z31_SUM - CHAR(14)
   '00000000000000', --Z31_VAT_SUM - CHAR(14)
   '$z31_sum', --Z31_NET_SUM - CHAR(14)
   '$z31_payment_date_key', --Z31_PAYMENT_DATE_KEY - CHAR(12), YYYYMMDDHHMM
   'BankId', --Z31_PAYMENT_CATALOGER
   '', --Z31_PAYMENT_TARGET
   '$remote_host', --Z31_PAYMENT_IP
   null, --Z31_PAYMENT_RECEIPT_NUMBER
   null, --Z31_PAYMENT_MODE
   null, --Z31_PAYMENT_IDENTIFIER
   '$cash_description', --Z31_DESCRIPTION
   null, null, --Z31_KEY, /Z31_KEY_TYPE
   null, null, null, --Z31_TRANSFER_DEPARTMENT, Z31_TRANSFER_DATE, Z31_TRANSFER_NUMBER
   null, null, null, --Z31_RECALL_TRANSFER_STATUS, Z31_RECALL_TRANSFER_DATE, Z31_RECALL_TRANSFER_NUMBER
   null, null, --Z31_RELATED_Z31_KEY, Z31_RELATED_Z31_KEY_TYPE
   null, --Z31_REQUESTER_NAME
   '$z31_update_time_stamp', --Z31_UPD_TIME_STAMP / CHAR(15)
   null, --Z31_PAYMENT_IP_V6
   null --Z31_NOTE              
   )" );

   $sth_fee->execute or run_exemption ("Error inserting new cash fee to database (z31 table): ".$DBI::errstr, 'warning'); #it is error, but do not interrupt registration process to user
   $sth_fee->finish();
   #generate circulation log (z309) row
   my $z309_rec_key = RPad($bor_id,12,' ').$z31_update_time_stamp;
   my $z309_rec_key_3 = RPad('0',15,'0');
   my $z309_rec_key_4 = RPad('0',27,'0');
   my $z309_date_x = strftime "%Y%m%d%H%M", localtime;
   my $sth_circlog = $dbh->prepare("insert into z309 (Z309_REC_KEY, Z309_REC_KEY_2, Z309_REC_KEY_3, Z309_REC_KEY_4, Z309_CATALOGER_NAME, Z309_CATALOGER_IP, Z309_DATE_X, Z309_ACTION, Z309_OVERRIDE, Z309_TEXT, Z309_DATA, Z309_UPD_TIME_STAMP, Z309_REQUEST_NUMBER, Z309_CATALOGER_IP_V6, Z309_PHOTO_REQUEST_NUMBER) values (
   '$z309_rec_key', --Z309_REC_KEY - CHAR(27)
   '000000000', --Z309_REC_KEY_2 - CHAR(9)
   '$z309_rec_key_3', --Z309_REC_KEY_3 - CHAR(15)
   '$z309_rec_key_4', --Z309_REC_KEY_4 - CHAR(27)
   'BankId', --Z309_CATALOGER_NAME
   '$remote_host', --Z309_CATALOGER_IP
   '$z309_date_x', --Z309_DATE_X - CHAR(12)
   $circ_log_action, -- Z309_ACTION - NUMBER(2)
   'N', --Z309_OVERRIDE
   '$circ_log_text', --Z309_TEXT
   '$circ_log_text', --Z309_DATA
   '".$z309_date_x."000', --Z309_UPD_TIME_STAMP - CHAR(15)
   0, --Z309_REQUEST_NUMBER - NUMBER(9)
   null, --Z309_CATALOGER_IP_V6
   0 --Z309_PHOTO_REQUEST_NUMBER - NUMBER(9)   
   )");
   $sth_circlog->execute or run_exemption ("Error inserting circulation log entry to database (z309 table): ".$DBI::errstr, 'warning'); #it is error, but do not interrupt registration process to user
   $sth_circlog->finish();

   print LOGFILE "	writing patron, cash and circ. \n";
   #JSON response to browser
   print '{"func": "registrate", "response": "ok"}'."\n";
   
   #send invitation (confirmation) e-mail to patron
   if ( $mail2patron_url ) {
      #20231010 pridano encodovani url
      my $bor_login_enc = uri_escape($bor_login); my $bor_password_enc=uri_escape($bor_password);
      $mail2patron_url =~ s/{{login}}/$bor_login_enc/;
      $mail2patron_url =~ s/{{password}}/$bor_password_enc/;
      print LOGFILE "      sending confirmation email to patron - calling service $mail2patron_url\n";
      my $ua_mail = LWP::UserAgent->new;
      my $send_mail = $ua_mail->get($mail2patron_url);
      unless ( $send_mail->is_success ) { run_exemption ("Error while sending email to patron: call $mail2patron_url  - returns:".$send_mail->status_line()."\n",'warning'); }
      }
   print LOGFILE "END registratePatron  \n\n\n";
   close (LOGFILE);
   return 1;
   } #sub registratePatron END


sub checkToken {
#checks valid session token in Oracle msvk_bankid table
#    The token is got from bankid service
#    This check is performed in all calls of this cgi expcept the first one to maintance the session  
   my ($stoken) = @_;
   unless ( $dbh->selectrow_array( "select count(*) from msvk_bankid where token='$stoken' and to_char(timestamp,'YYYYMMDD')='$today'" ) ) {
      run_exemption ("invalid token - $token",'error');
      }
   }


sub getMail { #Matyas 20230719
   #Using Aleph API, returns patron e-mail from Aleph data
   #sub is used if person data from Bankid contain no e-mail.
   print LOGFILE "$timestamp getMail $remote_addr \n";
   my $token=$comm_in->param('token') ;
   checkToken($token);
   unless ( $comm_in->param('bor_id') ) { run_exemption ("function getMail, parametr bor_id is missing",'warning'); return 0;}
   #call api to get mail
   my $x= $comm_in->param('bor_id');
   my $uam = LWP::UserAgent->new;
   $uam->timeout(10);
   my $uam_response = $uam->get( $xserver_url.'?op=bor-info&library='.$adm_base_upper.'&bor_id='.$x.'&user_name='.$xserver_upd_bor_user.'&user_password='.$xserver_upd_bor_password );
   unless ( $uam_response->is_success() ) { run_exemption ("Error calling x-server for bor-info. Call $xserver_url  -- returns ".$uam_response->status_line()."\n",'warning'); return 0; }
   my $y = $uam_response->decoded_content();
   my $yx = XMLin( $y, ForceArray => 1, KeyAttr => {} );
   if (  $yx->{error}  ) { run_exemption ("Error calling x-server for bor-info. returns error ".$y->{error}[0], 'warning'); }
   unless ( $yx->{z304} ) { run_exemption ("Error calling x-server for bor-info. Response does not contain z304 element", 'warning'); }
   unless ( $yx->{z304}[0]->{'z304-email-address'} ) { run_exemption ("Patron record in Aleph does not contain e-mail address.", 'warning');  }
   my $m = $yx->{z304}[0]->{'z304-email-address'}[0];
   if ( ref($m) eq 'HASH' ) { #if no adress, returns empty hash
       print LOGFILE "no email address\n";
       print '{"func": "get_mail", "mail": ""}'."\n" ;
       }
   else {
      print LOGFILE "found email address $m\n\n";
      print '{"func": "get_mail", "mail": "'.$m.'"}'."\n";         
      }
   }

sub getPatronStatus {
   #input: age (integer), 
   #       bor_status (string, optional)  
   #returns: patron status code (string),
   #         patron status name (string)
   my ($bor_age, $new_bor_status) = @_;
   my $sbor_status = $patron_bor_status_default;
   unless ( $bor_age )  { run_exemption ("Patron age was not recognised, adding universal status to him/her",'warning'); }
   unless ( $bor_age =~ /^\d+$/ )  { run_exemption ("Patron age $bor_age is not a whole number, adding universal status to him/her",'warning'); }
   if ( $bor_age < $patron_minimal_age ) { run_exemption ("Patron age is lower than $patron_minimal_age, cannot be registrated", 'error'); }
   #check statuses to be preserved
   my $preserve_status=0;
   if (defined $new_bor_status) {
      if ( grep( /^$new_bor_status$/, @current_bor_status_preserve )  ) {
         $sbor_status = $new_bor_status;
         $preserve_status=1; 
         }   
      }
   unless ( $preserve_status ) {
      #children status
      if ( $child_max_age and $child_bor_status ) {
         if ( $bor_age <= $child_max_age ) {  $sbor_status = $child_bor_status; }
         }    
      #youth status
      elsif ( $youth_max_age and $youth_bor_status ) {##BEN  if - elsif
         if ( $bor_age >= $patron_minimal_age and $bor_age > $child_max_age and $bor_age <= $youth_max_age ) {  $sbor_status = $youth_bor_status; }
         }    
      #retired status
      elsif ( $retired_min_age and $retired_bor_status ) {##BEN  if-elsif
         if ( $bor_age >= $retired_min_age ) {  $sbor_status = $retired_bor_status; }
         }
##BEN      #others, except preregistrated
	  elsif ($new_bor_status and $new_bor_status ne $bor_status_preregistrated) { $sbor_status=$new_bor_status;}##BEN 	 pridano
      }
   #get patron status name from tab table
   my $sbor_status_name='';
   open(my $fh_exp, '<', $tab_pc_tab_exp_field_extended) or run_exemption ("Cannot open tab_pc_tab_exp_field_extended.lng file with patron name definitions - $tab_pc_tab_exp_field_extended",'warning');
   while (my $row_exp = <$fh_exp>) {
      chomp $row_exp;
      if ( $row_exp =~ /^\s*\!/ ) { next; } #skip comments
      if ( substr($row_exp,0,10) eq 'BOR-STATUS' and substr($row_exp,80,2) eq $sbor_status ) {
         $sbor_status_name = substr($row_exp,29,50);
         last;
         }
      }
   unless ( $sbor_status_name ) {
      run_exemption ("Patron status name for status $sbor_status was not found in table $tab_pc_tab_exp_field_extended",'warning');
      return ($sbor_status, '');
      }
   $sbor_status_name =~ s/\s+$//;
   #y $sbor_status_name_utf = encode("UTF-8", decode("cp1250", $sbor_status_name));
   my $sbor_status_name_utf =  decode("cp1250", $sbor_status_name);
   print LOGFILE "	patron status: $sbor_status - $sbor_status_name\n";
   return ( $sbor_status, $sbor_status_name_utf );  
   }


sub getRegistrationFee {
   #looks up registration fee in fees defintion table tab18.lng
   #input: borrower status code - string(2)
   #       new_bor - string or alike. If true, fee code 0021 is taken (new registration), otherwisee fee code 0022 (registration renewal)
   #returns: registrations fee - string(!), including two digits after decimal point (i.e. '10000' = 100.00)
   #         fee_type - string(4) : #fee code 0021 is for new reg., 0022 for reg. renewal
   #get fee from tab18 table
   my ($sbor_status, $new_bor) = @_;
   my $fee_type = $new_bor ? '0022' : '0021'; #fee code 0021 is for new reg., 0022 for reg. renewal
   my $fee_sum = '';
   open(my $fh18, '<', $tab18_file) or run_exemption ("Cannot open tab18.lnge with fees definitions - $tab18_file",'error');
   while (my $row18 = <$fh18>) {
     chomp $row18;
     if ( $row18 =~ /^\s*\!/ ) { next; } #skip comments
     if ( substr($row18,0,4) eq $fee_type and ( substr($row18,14,2) eq $sbor_status or substr($row18,14,2) eq '##' ) ) { #line with fee definition
        $fee_sum = substr($row18,19,10); #including two digits after decimal point
        $fee_sum =~ s/\s+//g; 
        $fee_sum =~ s/\.//; 
        unless ( $fee_sum =~ /^[0-9r]+$/ ) { run_exemption ("Error in registration fee from $tab18_file - amount $fee_sum from line $row18 does not look as a number",'error'); }
        }
     }
   unless ( $fee_sum ) { run_exemption ("Error - registration fee definition not found in file $tab18_file for patron status $sbor_status",'error'); }
   print LOGFILE "	registration fee: $fee_sum\n";
   return ($fee_sum, $fee_type);
   }



sub age {
    #counts age on base or birth and current days
    # input: birth date: YYYYMMDD (string), output: age (integer)
    my ($birth_date) = @_;
    my $birth_year=substr($birth_date,0,4);
    my $birth_month=substr($birth_date,4,2); $birth_month =~ s/^0//; $birth_month--; #perl count months as 0..11
    my $birth_day=substr($birth_date,6,2); $birth_day =~ s/^0//;
    my ($day, $month, $year) = (localtime)[3..5];
    $year += 1900;
    my $age = $year - $birth_year;
    $age-- unless sprintf("%02d%02d", $month, $day)
    >= sprintf("%02d%02d", $birth_month, $birth_day);
    return $age;
    }



    
sub RPad {
   my ($str, $len, $chr) = @_;
   $chr = " " unless (defined($chr));
   $str = " " unless (defined($str));
   return substr($str . ($chr x $len), 0, $len);
   }
sub LPad {
   my ($str, $len, $chr) = @_;
   $chr = " " unless (defined($chr));
   return substr(($chr x $len) . $str, -1 * $len, $len);
   }



sub run_exemption {
   #exception/exemption/error/warning subroutine
   #parameters: 1. error text, 2. error level ("error" means critical)
   my $error_message = $_[0];
   my $error_level = '';
      if ( $_[1] ) { $error_level = $_[1]; }
   print LOGFILE $timestamp.' -- '.$remote_addr.' -- error : '.$error_message."\n";
   open(MAIL, "|/usr/sbin/sendmail -t");
   binmode MAIL, ":encoding(UTF-8)";
   print MAIL "To: ".$admin_mail."\n";
   print MAIL 'From: aleph@svkos.cz'."\n";
   print MAIL 'Subject: Error in bankid.cgi'."\n\n";
   print MAIL $timestamp.' -- '.$remote_addr.' -- error : '.$error_message."\n";
   my $error_message4json=$error_message; $error_message4json =~ s/".+$//g;
   print '{ "response": "error", "text": "'.$error_message4json.'", "level": "'.$error_level.'" }'."\n";
   if ( $error_level eq 'error' ) { print MAIL "\nFATAL ERROR !\n"; }
   close(MAIL);
   if ( $error_level eq 'error' ) {
      close(LOGFILE);
      if ( $dbh ) { $dbh->disconnect; }
      exit 0;}
   }

