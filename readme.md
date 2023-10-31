# Aleph - Registrace �ten��e online ov��en�m Bankovn� Identititou (BankId)

Roz���en� pro online registraci a prodlou�en� registrace v syst�mu ALEPH, kdy jsou z�sk�ny ov��en� �daje �ten��e pomoc� [Bankovn� identity - BankId](https://www.bankid.cz/). Pomoc� tla��tka/odkazu na www str�nk�cH, OPACu apod. je �ten�� nasm�rov�n na BankID. Zde p�i �sp�n�m ov��en� jsou z�sk�ny jeho osobn� �daje a p�ed�ny backend skriptu (cgi perl) k zpracov�n�. Zde se ov���, zda je �ten�� nov�, je ji� registrov�n (a m� vypr�enou nebo kon��c� registraci), p��p. voliteln� jestli byl registrov�n online bez ov��en� ("p�edregistrov�n").

Osobn� data z�skan� z BankID se zpracuj� do form�tu pro import do ALEPH a dopln� se o v�choz� hodnoty a nastaven� parametry. Nov�m a p�edregistrovan�m je vygenerov�n dle vlastn� nov� "pr�kaz" slou��c� dle nastaven� Alephu i jako login (typ Aleph id lze parametrizovat). Dle nastaven�ch parametr� lze na z�klad� v�ku �ten��e stanovit jeho status a typ, resp. zablokovat registraci do ur�it�ho v�ku. 

�ten�� je pot� vyzv�n k zad�n� hesla k st�vaj�c�mu nebo nov�mu vygenoravn�mu loginu (pr�kazu). Pokud je dr�itelem pr�kazu oprav�uj�c�ho k zvl�tn�mu statutu �ten��e, ale tato data nejsou z�sk�na z BankId, jako nap�. ZTP, m��e nahr�t scan/foto tohoto dokladu a ten je posl�n na e-mail registra�n�ho odd�len� knihovny, kde ru�n� posoud� a uprav� status �i poplatky.
Po za�krtnut� souhlasu s knihovn�m ��dem se �ten�� m��e registrovat. Potvrzen�m registrace dojde k z�pisu osobn�ch dat do Alephu pomoc� API (XServer) a skrze datab�zi k z�pisu registra�n�ho poplatku (ov��uje se dle nastaven� Alephu tab31) a z�znamu o online registraci do logu v�p�j�ek (z309). Pokud je OPAC napojen na platebn� br�nu dal��m roz���en�m, lze poplatek uhradit online.

O online registraci lze p�idat z�znam do pozn�mky �ten��e, vytv��� z�znam ve v�p�j�n�m logu a pro administr�tora je bankid.log v cgi adres��i.

## Requirements, Languages
ALEPH ver. 22 and above with XServer API license
Perl from Aleph distribution (with modules used in this distribution)
Apache with CGI
Javascript ES10 (ECMAScript 2019)

## Skripty etc.
Backend - perl cgi skript pro ov��ov�n� token�, dat v Alephu, jejich z�pis

Frontend - html, javascript pro komunikaci s Bankid, u�ivatelem v prohl�e�i a backendem
Oracle tabulka - pro pr�b�n� z�pis a sledov�n� session a dat registrovan�ho �ten��e

## Implementace
1. Roz���en� vy�aduje **registraci knihovny u Bankovn� identity** https://www.bankid.cz  Pro testov�n� lze vyu��t sandbox (nastaviteln� v main.js). Ov��en� osobn�ch dat ze strany BankId je  placenou slu�bou. V registraci z�sk�te client_id, nastav�te cestu k n�vratu (userinfo.html) a m��ete modifikovat texty p�i ov��ov�n�.

2. V administrativn� b�zi Alephu (xxx50) vytvo�it **Oracle tabulku** `msvk_bankid` a indexy pou��vanou skripty:
> create table msvk_bankid ( timestamp date, token varchar2(2000), bor_id varchar2(12), bor_login varchar2(20), bor_status char(2), registration_fee varchar2(22), fee_type char(4),  patron varchar2(4000), new_patron char(1) );
> create index ind_msvkbankid_token on msvk_bankid (token);
> create index ind_msvkbankid_timestamp on msvk_bankid (timestamp);	
> create index ind_msvkbankid_bor_login on msvk_bankid (bor_login);

3. **Backend skripty** - soubory `bankid.cgi` a `bankid.config` nahrajte do CGI adres��e Apache. V `bankid.config` jsou parametry backend skriptu a v�t�ina nastaven� v�bec, upravte dle vlastn�ch pot�eb a situace. Popis parametr� je v koment���ch v tomto souboru.

Pokud budete pou��vat mo�nost nahr�n� scanu pr�kazu (ZTP apod.) nahrejte do cgi adres��e t� soubor `bankid_file.cgi` pro upload souboru na server. V souboru upravte ��st ##PARAMETETERS, kde je email, kam m� b�t scan dokladu posl�n, adres�� pro ulo�en� souboru na server a dal��. 

3. **Frontend skripty** - optim�ln� je um�stit do samostatn�ho www p��stupn�ho adres��e, nap�. .../htdocs/bankid   Do tohoto adres��e nahrejte soubory `main.js`, `userinfo.html`, `userinfo.js`, `userinfo.css`, p��padn� p�ilo�en� BankId png obr�zky jako logo a tla��tko registrace p�es BankId.
  
`main.js`

Skript volan� z inicia�n� str�nky, kde je tla��tko/odkaz registrovat p�e bankid. Inicia�n� str�nkou m��e b�t Aleph opac template `bor-new`. P��klad pou�it� najdete v souboru `bor-new.example`, kter� obsahuje jen registraci BankId ov��en�m a m��ete k�d vlo�it do st�vaj�c�ho pou��van�ho souboru �ablony. 

Do head sekce je zde vlo�en odkaz na javascript (cestu p��padn� upravte):
> <script src="&server_httpd/bankid/main.js" defer></script>
D�le je v `bor-new.example` �vodn� text, odkaz do bankid napln�n� skrze main.js a bitmapov� nebo vektorov� tla��tko BankId.

V `main.js` je lze p�ep�nat mezi sandboxem a produk�n�m prost�ed�m BankId skrze konstanty authEndpoint a userInfoEndpoint. Nutno zde nastavit client_id (z�skan� p�i registraci v bankid) a redirect_uri (�pln� cesta k souboru userinfo.html).

`userinfo.html`, `userinfo.js`, `userinfo.css`  

Sem je u�ivatel nasm�rov�n po ov��en� v BankID. V `userinfo.js` m��ete konstantou userInfoEndpoint p�ep�nat sandbox a produk�n� prost�ed� BankId. D�le zde nastavte konstanty pro cestu v backendskriptu bankid.cgi, p��padn� pokud pou�ijete upload dokladu do ZTP apod. cestu k skriptu pro upload souboru. Nap�.:
> const backend = '/cgi-bin/bankid.cgi';
> const backendFileUpload = '/cgi-bin/bankid_file.cgi';

V `userinfo.html` jsou jednotliv� sou��sti/texty www str�nky zobrazovan�, skr�van� a dopl�ovan� pomoc� id atribut� ovl�dan�ch userinfo.js skriptem. Upravte texty �i chov�n� dle pot�eby, stejn� jako CSS.

4. Nastavte **�vodn� tla��tko/odkaz** pro registraci pomoc� BankID do webu knihovny, OPAC apod. Vzorov� p��klad je v opac www �ablon� `bor-new.example`   


