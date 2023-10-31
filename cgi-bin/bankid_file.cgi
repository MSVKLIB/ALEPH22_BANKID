#!/exlibris/aleph/a22_1/product/bin/perl
#part of bankovni identita - bankid registration
#
#upload file with document allowing free of charge registration
#the file is send to library address
#
#input: ztp_file - file, bor_name = cislo ctenare login
#output: text/plain ("ok" if all done}
#
#Made by Matyas Bajger, 2023, License CC BY NC 4.0		
#
use strict;
use warnings;
use DBI;
#use CGI ':utf8';
#TODOuse CGI qw(-utf8);
use CGI qw(param);
use MIME::Lite;
use Data::Dumper;
use DBI;
use POSIX qw/strftime/;
use File::Copy;
$ENV{NLS_LANG} = 'AMERICAN_AMERICA.AL32UTF8';
local $/=undef;


##PARAMETETERS
our $registration_email = 'registrace@msvk.cz'; #email address to which the uploaded file will be send
our $from_email = 'aleph@library.any'; #from "who"  file will be send
our $upload_dir = "/tmp"; #where uploaded file will be stored on servers
our $adm_base = 'xxx50'; #lower case
our $sid = 'dbi:Oracle:host=localhost;sid=aleph23'; #oracle SID
#####


my $today = strftime "%Y%m%d", localtime;
my $timestamp = strftime "%Y%m%d-%H:%M:%S", localtime;
my $query = new CGI;
my $resp = new CGI;
open ( LOGFILE, ">>bankid.log" );
binmode LOGFILE, ":encoding(UTF-8)";


print $resp->header(-type => "text/plain");


unless ( $query->param("ztp_file") ) { print "error - parameter ztp_file is missing\n"; die }
my $bor_name = $query->param("bor_name") ? $query->param("bor_name") : "noname-$today";

my $filename = $query->param("ztp_file");
$filename =~ s/.*[\/\\](.*)/$1/;

my $token = $filename; 
$token =~ s/\.[^\.]+$//;
my $filename_extension=$filename; 
$filename_extension =~ s/^.+\.([^\.]+)$/$1/;
$filename =~ s/\.[^\.]+$//;
$filename = substr($filename,0,100);
$filename .= '.'.$filename_extension;
print LOGFILE "$timestamp bankid_file.cgi - file $filename uploaded\n";
checkToken($token);
print LOGFILE "$timestamp bankid_file.cgi - check token passed\n";

#save file
my $upload_filehandle = $query->upload("ztp_file");
unless ( $upload_filehandle ) { print "error - file cannot be uploaded, no filehandle\n"; die; }
my $f2s="$upload_dir/prukaz_$bor_name".".$filename_extension";
unless (open UPLOADFILE, ">$f2s") { print "error - cannot save to file $f2s \n"; die; }#
while ( <$upload_filehandle> )
  { print UPLOADFILE; }
close UPLOADFILE;
print LOGFILE "$timestamp bankid_file.cgi - file saved to $f2s \n";

#send mail
my $file_type;

# Nastavení proměnné $file_type na základě přípony souboru
if ($filename_extension =~ /^jpg|jpeg$/i) {
    $file_type = 'image/jpeg';
} elsif ($filename_extension =~ /^png$/i) {
    $file_type = 'image/png';
} elsif ($filename_extension =~ /^gif$/i) {
    $file_type = 'image/gif';
} elsif ($filename_extension =~ /^pdf$/i) {
    $file_type = 'application/pdf';
} else {
    $file_type = 'application/pdf';
}

my $subject="Online registrace - prukaz pro $bor_name";
my $message = 'Prilozena kopie dokladu opravnujiciho k registraci zdarma. Prosim, overit. Vas Aleph';


my $msg = MIME::Lite->new(
                From    => $from_email,
                To      => $registration_email,
                Subject  => $subject,
                Type    => 'multipart/mixed'
                );

# Add your text message.
$msg->attach(Type         => 'text',
            Data        => $message
            );

# Specify your file as attachement.
#$msg->attach(Type         => 'image/gif','image/png',
$msg->attach(Type         => $file_type,
            Path        => $f2s,
            Filename    => 'prukaz.'.$filename_extension,
            Disposition  => 'attachment'
          );       
unless ( $msg->send ) { print "error - cannot send e-mail to library\n"; die; }
#unless ( $msg->send('sendmail', "/usr/lib/sendmail -t -oi ") ) { print "error - cannot send e-mail to library\n"; die; }
#does not work $msg->send ('smtp','fialka.svkos.cz', Debug=>1 );

print LOGFILE "$timestamp bankid_file.cgi - file mailed to $registration_email\n\n";

print "ok\n";



sub checkToken {
   my ($stoken) = @_;
   if ( length($stoken) < 100 ) { print "error - t o k e n too short $stoken\n"; die; }
   my $dbh = DBI->connect($sid, $adm_base, $adm_base, {AutoCommit => 1});
   unless ( $dbh ) { print "error couldn't connect to database - ".$DBI::errstr."\n"; die; }
   my @t = $dbh->selectrow_array( "select count(1) from msvk_bankid where token like '$stoken%' and to_char(timestamp,'YYYYMMDD')='$today'" ) ;
   unless ( @t) { print "error - invalid t o k e n\n"; die; }
   }

