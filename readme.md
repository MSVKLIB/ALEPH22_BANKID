# Aleph - Registrace ètenáøe online ovìøením Bankovní Identititou (BankId)

Rozšíøení pro online registraci a prodloužení registrace v systému ALEPH, kdy jsou získány ovìøené údaje ètenáøe pomocí [Bankovní identity - BankId](https://www.bankid.cz/). Pomocí tlaèítka/odkazu na www stránkácH, OPACu apod. je ètenáø nasmìrován na BankID. Zde pøi úspìšném ovìøení jsou získány jeho osobní údaje a pøedány backend skriptu (cgi perl) k zpracování. Zde se ovìøí, zda je ètenáø nový, je již registrován (a má vypršenou nebo konèící registraci), pøíp. volitelnì jestli byl registrován online bez ovìøení ("pøedregistrován").

Osobní data získaná z BankID se zpracují do formátu pro import do ALEPH a doplní se o výchozí hodnoty a nastavené parametry. Novým a pøedregistrovaným je vygenerován dle vlastní nový "prùkaz" sloužící dle nastavení Alephu i jako login (typ Aleph id lze parametrizovat). Dle nastavených parametrù lze na základì vìku ètenáøe stanovit jeho status a typ, resp. zablokovat registraci do urèitého vìku. 

Ètenáø je poté vyzván k zadání hesla k stávajícímu nebo novému vygenoravnému loginu (prùkazu). Pokud je držitelem prùkazu opravòujícího k zvláštnímu statutu ètenáøe, ale tato data nejsou získána z BankId, jako napø. ZTP, mùže nahrát scan/foto tohoto dokladu a ten je poslán na e-mail registraèního oddìlení knihovny, kde ruènì posoudí a upraví status èi poplatky.
Po zaškrtnutí souhlasu s knihovním øádem se ètenáø mùže registrovat. Potvrzením registrace dojde k zápisu osobních dat do Alephu pomocí API (XServer) a skrze databázi k zápisu registraèního poplatku (ovìøuje se dle nastavení Alephu tab31) a záznamu o online registraci do logu výpùjèek (z309). Pokud je OPAC napojen na platební bránu dalším rozšíøením, lze poplatek uhradit online.

O online registraci lze pøidat záznam do poznámky ètenáøe, vytváøí záznam ve výpùjèním logu a pro administrátora je bankid.log v cgi adresáøi.

## Requirements, Languages
ALEPH ver. 22 and above with XServer API license
Perl from Aleph distribution (with modules used in this distribution)
Apache with CGI
Javascript ES10 (ECMAScript 2019)

## Skripty etc.
Backend - perl cgi skript pro ovìøování tokenù, dat v Alephu, jejich zápis

Frontend - html, javascript pro komunikaci s Bankid, uživatelem v prohlížeèi a backendem
Oracle tabulka - pro prùbìžný zápis a sledování session a dat registrovaného ètenáøe

## Implementace
1. Rozšíøení vyžaduje **registraci knihovny u Bankovní identity** https://www.bankid.cz  Pro testování lze využít sandbox (nastavitelný v main.js). Ovìøení osobních dat ze strany BankId je  placenou službou. V registraci získáte client_id, nastavíte cestu k návratu (userinfo.html) a mùžete modifikovat texty pøi ovìøování.

2. V administrativní bázi Alephu (xxx50) vytvoøit **Oracle tabulku** `msvk_bankid` a indexy používanou skripty:
> create table msvk_bankid ( timestamp date, token varchar2(2000), bor_id varchar2(12), bor_login varchar2(20), bor_status char(2), registration_fee varchar2(22), fee_type char(4),  patron varchar2(4000), new_patron char(1) );
> create index ind_msvkbankid_token on msvk_bankid (token);
> create index ind_msvkbankid_timestamp on msvk_bankid (timestamp);	
> create index ind_msvkbankid_bor_login on msvk_bankid (bor_login);

3. **Backend skripty** - soubory `bankid.cgi` a `bankid.config` nahrajte do CGI adresáøe Apache. V `bankid.config` jsou parametry backend skriptu a vìtšina nastavení vùbec, upravte dle vlastních potøeb a situace. Popis parametrù je v komentáøích v tomto souboru.

Pokud budete používat možnost nahrání scanu prùkazu (ZTP apod.) nahrejte do cgi adresáøe též soubor `bankid_file.cgi` pro upload souboru na server. V souboru upravte èást ##PARAMETETERS, kde je email, kam má být scan dokladu poslán, adresáø pro uložení souboru na server a další. 

3. **Frontend skripty** - optimální je umístit do samostatného www pøístupného adresáøe, napø. .../htdocs/bankid   Do tohoto adresáøe nahrejte soubory `main.js`, `userinfo.html`, `userinfo.js`, `userinfo.css`, pøípadnì pøiložené BankId png obrázky jako logo a tlaèítko registrace pøes BankId.
  
`main.js`

Skript volaný z iniciaèní stránky, kde je tlaèítko/odkaz registrovat pøe bankid. Iniciaèní stránkou mùže být Aleph opac template `bor-new`. Pøíklad použití najdete v souboru `bor-new.example`, který obsahuje jen registraci BankId ovìøením a mùžete kód vložit do stávajícího používaného souboru šablony. 

Do head sekce je zde vložen odkaz na javascript (cestu pøípadnì upravte):
> <script src="&server_httpd/bankid/main.js" defer></script>
Dále je v `bor-new.example` úvodní text, odkaz do bankid naplnìný skrze main.js a bitmapové nebo vektorové tlaèítko BankId.

V `main.js` je lze pøepínat mezi sandboxem a produkèním prostøedím BankId skrze konstanty authEndpoint a userInfoEndpoint. Nutno zde nastavit client_id (získané pøi registraci v bankid) a redirect_uri (úplná cesta k souboru userinfo.html).

`userinfo.html`, `userinfo.js`, `userinfo.css`  

Sem je uživatel nasmìrován po ovìøení v BankID. V `userinfo.js` mùžete konstantou userInfoEndpoint pøepínat sandbox a produkèní prostøedí BankId. Dále zde nastavte konstanty pro cestu v backendskriptu bankid.cgi, pøípadnì pokud použijete upload dokladu do ZTP apod. cestu k skriptu pro upload souboru. Napø.:
> const backend = '/cgi-bin/bankid.cgi';
> const backendFileUpload = '/cgi-bin/bankid_file.cgi';

V `userinfo.html` jsou jednotlivé souèásti/texty www stránky zobrazované, skrývané a doplòované pomocí id atributù ovládaných userinfo.js skriptem. Upravte texty èi chování dle potøeby, stejnì jako CSS.

4. Nastavte **úvodní tlaèítko/odkaz** pro registraci pomocí BankID do webu knihovny, OPAC apod. Vzorový pøíklad je v opac www šablonì `bor-new.example`   


