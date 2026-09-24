# مسرد الترجمة العربية — Controglobe Arabic glossary

This file is the **binding authority** for every proper noun in the Arabic edition
(`ar/`). A name is decided once here and used identically in every article. If you
translate a page and meet a name that is missing, choose a rendering, use it
throughout, and append it here in the same pass.

## Conventions

- **Register:** Modern Standard Arabic, encyclopedic, past tense for history, in the
  manner of ar.wikipedia. The subject is bolded in the first sentence of the lead.
- **First mention:** an invented proper noun gives its Latin form once, in
  parentheses — المشرق (بالإنجليزية: al-Mashriq) — and never again on that page.
- **Numerals:** Western Arabic digits (1776، 24، 1.71), as on ar.wikipedia.
  Eras: BCE → ق.م، CE → م.
- **Code is not translated.** `id` values, `href="#anchors"`, `data-pv` keys and the
  keys of `PV` / `LINKS` stay Latin, so links keep working across both editions.
  The keys of `MATCH`, which are on-page display text, *are* translated.
  JavaScript comments stay in English; user-visible strings in the script do not.
- **Transliterations stay Latin.** Where the English page prints a romanised Arabic
  term in italics as a gloss (`al-Ittiḥād al-Nabaṭī`, `ʻAhd al-Ābār`, `ḥakam kātib`),
  the Arabic page keeps the Latin form beside the Arabic one, because it is there to
  show the romanisation. A real English Wikipedia article title cited as a structural
  model also stays in Latin.
- **MATCH keys are what `flat()` yields.** The page folds every whitespace run to a
  plain space before the lookup, so an Arabic key is written with plain spaces even
  where the prose prints `&nbsp;`.
- **SVG labels.** A label centred on a shape (`text-anchor="middle"`) is translated in
  place. Where a diagram's panels carry geometry that may not move, its start-anchored
  labels keep `direction="ltr"` so they stay anchored at their own `x`; only labels whose
  row can be mirrored (a map key) are moved across the canvas.
- **A key band is mirrored, and anchored at its own `start`.** The white band under a
  map holds rows that begin at the left edge in English. In the Arabic edition the row
  moves to the right edge and takes `direction="rtl"` with `text-anchor="start"` — in a
  right-to-left run `start` *is* the right-hand side, so `end` would anchor the wrong
  edge and run the row off the canvas.
- **Untranslated targets:** a link to an article that has no Arabic edition yet
  points at `../<file>.html` and carries `class="pending"`, which prints
  "(بالإنجليزية)" after it, the way an interlanguage red link behaves. When the
  Arabic edition of that article lands, drop `../` and drop the class. Every
  article is translated as of now, so nothing carries the class; the rule stays in
  the shared design system for the next article written in English first.
- **Numeric ranges are isolated.** Between two numbers the en-dash is a neutral and
  resolves right-to-left, so `1789&ndash;1797` would lay out as 1797 then 1789. Wrap
  such a range in U+2066 (LRI) and U+2069 (PDI) — invisible characters, no markup —
  and it reads left to right again. A range with an Arabic word on one side
  (`1967&ndash;الآن`) already reads correctly and is left alone.
- **A name written in its own language stays in it.** The swap-key table prints each
  polity's native name in parentheses (`Staat Ludwigsland`, `Estado de California`,
  `al-Jumhuriyyah al-Urighuniyyah`); that parenthesis is the name as its own speakers
  write it, so it is never converted to Arabic script, not even when the language is
  Arabic. The same holds for the romanisation under an infobox title: where the
  English page prints the Arabic name and its romanisation beneath an English title,
  the Arabic page puts the Arabic name in the title and keeps only the romanisation
  below, so the name is not printed three times.
- **The interlanguage link sits in `.cg-tools`.** The link carries the other language's
  `dir`, so a logical margin on the link itself would resolve against *its* direction. The
  masthead puts it inside `.cg-tools`, which has no `dir` of its own, and pushes that
  container to the far end instead; nothing on the page needs a physical margin.
- **Labels in generated maps.** The world and regional maps are drawn with `direction="ltr"`
  on the root `<svg>`, so geometry never moves. Their Arabic labels then carry
  `direction="rtl"` themselves, with the anchor flipped (`start` ↔ `end`) so that a label
  still sits on the same side of its point; a centred label only needs the direction.
- **Name Arabia by what is meant.** In running prose and on maps, the state is
  «الولايات المتحدة» and the land before 1776 is «الجزيرة العربية»; «العربية» alone is kept
  for headings inherited from the History article.

## Project and setting

| English | العربية | Note |
|---|---|---|
| Controglobe | كونتروغلوب | project name, transliterated |
| Global Swap | التبادل الكبير | the setting's central conceit |
| Global North / Global South | الشمال العالمي / الجنوب العالمي | |
| outside timeline | الخط الزمني الخارجي | i.e. our own history |
| worldbuilding | بناء العوالم | |
| canon | القانون المعتمد | |
| preview card | بطاقة المعاينة | |
| custom entity / custom nation | كيان مبتكر / أمة مبتكرة | |
| swap key | مفتاح التبادل | the section naming the outside-timeline counterpart |
| The Global Swap encyclopedia | موسوعة التبادل الكبير | the masthead tagline |
| Timeline (site link) | الخط الزمني | |
| Colour theme: match the system / light / dark | سمة الألوان: حسب النظام / فاتحة / داكنة | the masthead switch |
| Back to top / Skip to content | العودة إلى الأعلى / انتقل إلى المحتوى | |
| unassigned (no counterpart yet) | لم يُسنَد إليه نظير بعد | East Asia, northern Asia, Australia |

## Nations and polities

| English | العربية | Carries |
|---|---|---|
| United States of Arabia | الولايات المتحدة العربية | the United States |
| — short form | الولايات المتحدة | never «العربية» alone, which reads as the language |
| al-Mashriq | المشرق | |
| Zagrosia | زاغروسيا | Canada; Anatolia carries Quebec, Iran the rest |
| al-Mashriq (the bloc) | المشرق | the United States of Arabia, Zagrosia and Qubrus; Masr is the neighbour, not a member |
| Qubrus | قبرص | Greenland; self-governing, within al-Mashriq |
| Masr | مصر | Mexico |
| Wene wa Kongo | ويني وا كونغو | Germany |
| Kimfumu kya Kongo | كيمفومو كيا كونغو | the German Empire |
| Jolof | جولوف | Spain |
| Derg Union | اتحاد الدِرغ | Russia and the USSR |
| Hindustani Empire / Hindustan | الإمبراطورية الهندوستانية / هندوستان | Britain, Japan and China |
| Nusantara | نوسانتارا | China |
| Aïr | آير | custom (Niger) |
| Kong / Republic of Kong | كونغ / جمهورية كونغ | France |
| Kaabu | كابو | Portugal |
| Ndongo | ندونغو | Italy |
| Sokoto | سوكوتو | Britain |
| DN Kongo | دي إن كونغو | Austria; the initials are not expanded, so they are transliterated |
| Union of Zambezia | اتحاد الزامبيزيا | Yugoslavia; dissolved in the 1990s |
| Qumur | قُمُر | the in-world state; the islands themselves are جزر القمر |
| Fouta Djallon | فوتا جالون | Galicia |
| Saguia el-Hamra | الساقية الحمراء | the Faroes |
| Greater Lesotho | ليسوتو الكبرى | Kosovo |
| Xhosa Republic | جمهورية الخوسا | Greece |
| Cape Republic | جمهورية الكاب | custom; it carried Anatolia until Anatolia became Zagrosian |
| Kanem | كانم | custom (Chad) |
| Songhai | سنغاي | custom |
| Tem | تم | custom |
| Anglia | أنغليا | Great Britain; carries Nigeria |
| Rhenia | رينيا | Germany; carries the Congo |
| Francia | فرانكيا | France; carries the Ivory Coast |
| The Low Countries | البلدان المنخفضة | one state, three members; carries Cameroon |
| Kamerun | كاميرون | the polity; the outside-timeline country is الكاميرون |
| Sápmi | سابمي | custom; the same nation as Kanem, seen from the other end |
| Basque Country | بلاد الباسك | the twin of Songhai |
| Aquitaine / Brittany / Normandy | آكيتانيا / بريتاني / نورماندي | custom duchies |
| Galicia | غاليسيا | carries Guinea |
| Crimea | القرم | carries Somaliland |

## Institutions, events and terms

| English | العربية |
|---|---|
| Nabataean Unification | الوحدة النبطية |
| Covenant of the Wells | ميثاق الآبار |
| Well Rolls | سجلات الآبار |
| Custodianship of the Two Holy Mosques | الوِصاية على الحرمين الشريفين |
| Thirty-First Amendment | التعديل الحادي والثلاثون |
| Revolution of 1776 | ثورة 1776 |
| Civil War | الحرب الأهلية |
| khidmah | الخِدمة |
| saqaliba | الصقالبة |
| thirteen princely colonies | المستعمرات الأميرية الثلاث عشرة |
| Red Sea Company | شركة البحر الأحمر |
| Damascus Convention | مؤتمر دمشق |
| Treaty of Sohar | معاهدة صحار |
| Gulf War of 1898 | حرب الخليج 1898 |
| Mysore method | أسلوب ميسور |
| oil shocks | صدمات النفط |
| Kuwait Purchase | صفقة شراء الكويت |
| Manarat al-Hurriyyah | منارة الحرية |
| Mansa Jata | مانسا جاتا |
| Velvet Divorce | الطلاق المخملي |
| Nabataean Unification | الوحدة النبطية |
| Long Thirst | العطش الطويل |
| Well Rolls / Bureau of Wells | سجلات الآبار / ديوان الآبار |
| Masters of Water | أصحاب الماء |
| Commanders of the Road | قادة الدرب |
| Council of the Tribes | مجلس القبائل |
| Ordinance of Weights / Arabic Ordinance / Water Ordinance | مرسوم الموازين / مرسوم العربية / مرسوم الماء |
| chancery Arabic | العربية الديوانية |
| lettered arbitrators (ḥakam kātib) | المحكَّمون من أهل الكتابة |
| hima | الحِمى |
| Dedan settlement | تسوية ددان |
| War of the Two Capitals | حرب العاصمتين |
| Hisma dam chain | سلسلة سدود حسمى |
| Hegra archive | أرشيف الحِجر |
| oasis leagues | عصب الواحات |
| sela' (coin) | السَّلع |
| Dushara / Allat / al-'Uzza / Manat | ذو الشرى / اللات / العُزى / مناة |
| Aretas / Obodas / Malichus / Rabbel (kings) | الحارث / عبادة / مالك / ربئيل |
| compact school / national school | مدرسة العقد / المدرسة القومية |
| sayyārah / wanayt | سيّارة / ونيت |
| Rashid Motor Company / Rashid Model T | شركة الرشيد للسيارات / رشيد طراز T |
| Ittihad Motors | اتحاد موتورز |
| Basra Motor Works / Three of Mosul | مصانع البصرة للسيارات / ثلاثي الموصل |
| Malonga / Nsimba / Mafuta / Kalala Tshibangu | مالونغا / نسيمبا / مافوتا / كالالا تشيبانغو |
| Nkangu programme / Type 1 | برنامج نكانغو / طراز 1 |
| Josephine Kabongo / Nuri al-Rashid / Nadia Khoury | جوزفين كابونغو / نوري الرشيد / نادية خوري |
| Mysore Loom & Motor / the Mysore method | ميسور للأنوال والمحركات / أسلوب ميسور |
| chit class | طبقة الأقساط |
| Kilat / Kivu / Sanwi / Bouaké Motors | كيلات / كيفو / سانوي / بواكيه موتورز |
| Ombaka 275 / Awash 2101 / Ilorin / Tarma / Chasqui | أومباكا 275 / أواش 2101 / إيلورين / ترما / تشاسكي |
| Hamil / Hamil Wadi | الحامل / حامل وادي |
| Kinshasa Regulations | لوائح كينشاسا |
| Federal Standard 209 | المعيار الاتحادي 209 |
| Zagros Motor Agreement | اتفاق زاغروس للسيارات |
| Sinai Border Programme | برنامج حدود سيناء |
| Kinshasa–Helsinki Raid | سباق كينشاسا–هلسنكي |
| Najd ovals / Bouna 24 Hours | حلبات نجد البيضاوية / سباق بونا 24 ساعة |
| shade roof / the fin | السقف الظليل / الزعنفة |
| traffic side: left/right-hand bloc | جهة السير: الكتلة اليسارية / اليمينية |
| Lubumbashi / Kananga / Likasi / Kipushi / Kambove | لوبومباشي / كانانغا / ليكاسي / كيبوشي / كامبوفي |
| Surabaya / Sulawesi / Bangka | سورابايا / سولاويسي / بانغكا |
| Constanța / Rijeka / Tangier | كونستانتسا / رييكا / طنجة |
| Interregnum | حقبة الفترة |
| Saqaliba / Saqaliba Revolt | الصقالبة / ثورة الصقالبة |
| khidmah / tab'iyyah | الخِدمة / التبعية |
| Qayd laws | قوانين القَيد |
| Red Sea Company | شركة البحر الأحمر |
| thirteen princely colonies | المستعمرات الأميرية الثلاث عشرة |
| Najd Awakening / New Awakening | صحوة نجد / الصحوة الجديدة |
| Continental Majlis | المجلس القاري |
| Declaration of Independence | إعلان الاستقلال |
| Manumission Proclamation / Manumission Day | إعلان العتق / يوم العتق |
| Night Road (Darb al-Layl) | درب الليل |
| Road of Thirst (Darb al-'Atash) | درب العطش |
| Desert Removal Act | قانون ترحيل الصحراء |
| Islamic States of Arabia | الدول الإسلامية في الجزيرة العربية |
| Bleeding Shammar | شمر الدامية |
| Union party / Ahd / Sha'bi / Asalah | حزب الاتحاد / العهد / الشعبي / الأصالة |
| Umm al-Qura | أم القرى |
| Sanctuaries Act | قانون الحرمين |
| Sharifate of Makkah | شرافة مكة |
| Ikhwan al-Tawhid / Sabilla | إخوان التوحيد / السبلة |
| Great Migration | الهجرة الكبرى |
| Dust Years | سنوات الغبار |
| Alamut Project | مشروع ألموت |
| Umm al-Qura Pact / Recovery Programme | حلف أم القرى / برنامج التعافي |
| Adharbaijan | أذربيجان |
| Jazirat al-Wasit | جزيرة الواسط |
| Harat al-Yaman | حارة اليمن |
| European Arabians / al-Ifranji | العرب الأوروبيون / الإفرنجي |
| Federal Commission on Servitude | اللجنة الاتحادية للاسترقاق |
| OTL / the outside timeline | الخط الزمني الخارجي |
| Motor vehicles | المركبات الآلية |
| Europe — the African Swap | أوروبا — التبادل الأفريقي |
| mirror rule | قاعدة المرآة |
| Federation of the Sava | اتحاد السافا |
| Organisation of European Unity | منظمة الوحدة الأوروبية |
| European Union (seat at Moscow) | الاتحاد الأوروبي |
| Year of Europe | عام أوروبا |
| Kong Community | الجماعة الكونغية |
| Kong West Europe / Kong Central Europe | أوروبا الغربية الكونغية / أوروبا الوسطى الكونغية |
| Sokoto East Europe | أوروبا الشرقية السوكوتية |
| the Kamerunian estate | الضيعة الكاميرونية |
| Duala Company | شركة دوالا |
| Kong franc | الفرنك الكونغي |
| Humber secession | انفصال الهمبر |
| presidio at Gibraltar | حامية جبل طارق |
| recaptives | المحرَّرون المستردّون |

## Timeline of the Global Swap

| English | العربية |
|---|---|
| Timeline of the Global Swap | الخط الزمني للتبادل الكبير |
| the divergence / the first departure | الافتراق / الافتراق الأول |
| Before the divergence | ما قبل الافتراق |
| Antiquity and the Nabataean unification | العصور القديمة والوحدة النبطية |
| The caliphal centuries | قرون الخلافة |
| The age of the crowns | عصر التيجان |
| Revolution and expansion | الثورة والتوسع |
| Servitude, industry and the partition of Europe | الاسترقاق والصناعة وتقسيم أوروبا |
| The world wars | الحربان العالميتان |
| Arabia and the Derg Union | الولايات المتحدة واتحاد الدِرغ |
| After the Cold War | ما بعد الحرب الباردة |
| Achaemenids / the Achaemenid withdrawal | الأخمينيون / الانسحاب الأخميني |
| Gindibu / Qarqar / Nabonidus | جندب / قرقر / نبونيد |
| Hajr (the wells of the Covenant) | هجر |
| Sahib al-Saqaliba | صاحب الصقالبة |
| Lakhnau (the imperial seat) | لكهنؤ |
| Jizan / Massawa / Magan Town | جيزان / مصوّع / بلدة مجان |
| Hassaniya crown | التاج الحساني |
| Suez portage | مَحمل السويس |
| Frankish, Rhenish, Anglian and Slavic lands | البلاد الفرنجية والراينية والأنغلية والسلافية |
| the sea-raiders' coasts | سواحل غزاة البحر |
| Kinshasa airlift / Harar Pact | جسر كينشاسا الجوي / حلف هرر |
| Bornean War / Sulawesi War / Zanjibar | حرب بورنيو / حرب سولاويسي / زنجبار |
| Federal Chronology Office | ديوان التسلسل الزمني الاتحادي |

## Places

| English | العربية |
|---|---|
| Petra / Hegra | البتراء / الحِجر |
| Sela (the rock) | سلع |
| Dedan / Tayma / Duma | ددان / تيماء / دومة |
| Hisma / Hejaz / Najd | حسمى / الحجاز / نجد |
| Jabal Shammar / Yamama / Hawran | جبل شمر / اليمامة / حوران |
| Gerrha / Najran / Ma'rib | جرها / نجران / مأرب |
| Edom / Qedar / Lihyan | أدوم / قيدار / لحيان |
| Nabatu / al-Anbat | نبطو / الأنباط |
| Characene / Magan / Saba / Himyar | ميسان / مجان / سبأ / حمير |
| Lakhmids / Ghassanids | اللخميون / الغساسنة |
| Arabian Peninsula | شبه الجزيرة العربية |
| Levantine seaboard | الساحل الشامي |
| Tigris–Euphrates basin | حوض دجلة والفرات |
| Mosul | الموصل |
| Yalang Yalang | يالانغ يالانغ |
| Lubumbashi / Kinshasa | لوبومباشي / كينشاسا |
| Tibesti / Lake Chad | تيبستي / بحيرة تشاد |
| Macaronesia | ماكارونيزيا |
| Sápmi / the Alps | سابمي / الألب |
| Middle East | الشرق الأوسط |
| North America / South America | أمريكا الشمالية / أمريكا الجنوبية |
| Central America / Central Asia | أمريكا الوسطى / آسيا الوسطى |
| South Asia / mainland South Asia | جنوب آسيا / جنوب آسيا القاري |
| maritime South-East Asia | جنوب شرق آسيا البحري |
| the Caucasus / the Caribbean | القوقاز / الكاريبي |
| Indian Ocean / Pacific | المحيط الهندي / المحيط الهادئ |
| Iceland / Greenland / Cyprus / Morocco | آيسلندا / غرينلاند / قبرص / المغرب |
| Faroe Islands / Azores / Madeira / Canaries | جزر فارو / الأزور / ماديرا / الكناري |
| the Kuban | الكوبان |
| the Rhine / the Danube / the Vistula / the Tornio / the Prut | الراين / الدانوب / الفيستولا / تورنيو / بروت |
| the Carpathians / the Dinarides / the Pyrenees | الكاربات / الدينار / البرانس |
| Sicily / Sardinia / Malta / Crete | صقلية / سردينيا / مالطا / كريت |

## Hatnotes and furniture

| English | العربية |
|---|---|
| Main article: | مقالة مفصلة: |
| Main articles: | مقالات مفصلة: |
| Further information: | لمزيد من المعلومات: |
| See also: | انظر أيضًا: |
| § Section of … | § قسم من … |
| Featured article | مقالة مختارة |
| Reference atlas | أطلس مرجعي |

## Government, parties and the presidency

| English | العربية | Note |
|---|---|---|
| Majlis al-Ittihad | مجلس الاتحاد | the federal legislature |
| Majlis an-Nuwab (Chamber of Deputies) | مجلس النواب | lower house |
| Majlis al-Shuyukh (Council of Elders) | مجلس الشيوخ | upper house |
| Supreme Court | المحكمة العليا | |
| Supreme Waqf Council | المجلس الأعلى للأوقاف | |
| Custodianship of the Two Holy Mosques | الوِصاية على الحرمين الشريفين | a trust, not a personal title |
| Presidential House | دار الرئاسة | |
| Great Seal | الختم الأكبر | |
| Nth president | الرئيس الـ… / الرئيسة الـ… | the ordinal agrees in gender: الرئيسة الخامسة والعشرون |
| Islah / Asalah | إصلاح / أصالة | the two present-day parties, unarticled |
| Ahd / Union / Progressive | العهد / الاتحاد / التقدمية | historical parties |
| Ittihadi / Jumhuri / Sha'bi | الاتحادي / الجمهوري / الشعبي | |
| Non-partisan | مستقل | |
| Civil Service Act | قانون الخدمة المدنية | |
| Twenty-Fifth Amendment | التعديل الخامس والعشرون | |
| electoral college | المجمع الانتخابي | |
| impeachment | دعوى العزل | |

## Events, programmes and institutions

| English | العربية |
|---|---|
| Damascus Convention | مؤتمر دمشق |
| Farewell Address | خطاب الوداع |
| Charter of Liberties | ميثاق الحريات |
| Qasimi Doctrine | مبدأ القاسمي |
| Tihamah Compromise / Compromise of 1850 | تسوية تهامة / تسوية 1850 |
| Desert Removal Act | قانون ترحيل الصحراء |
| Panic of 1837 | ذعر 1837 |
| Second Bank of Arabia | مصرف العربية الثاني |
| fugitive servants law | قانون الخدم الآبقين |
| Hijaz–Jawf Act | قانون الحجاز–الجوف |
| Gilded Age | العصر المذهَّب |
| Great Society | المجتمع العظيم |
| Voting Rights Act | قانون حقوق التصويت |
| Aqaba accords | اتفاقات العقبة |
| Kartli Missile Crisis | أزمة صواريخ كارتلي |
| Green Arabia programme | برنامج العربية الخضراء |
| Wain movement | حركة وين |
| Umm al-Qura Pact | حلف أم القرى |
| Concert of Nations | محفل الأمم |
| World Heritage listing | إدراج في التراث العالمي |
| National Parks Act | قانون المتنزهات الوطنية |

## Economy, culture and everyday life

| English | العربية |
|---|---|
| Bitrularab | بترولعرب |
| Jeddah Exchange | بورصة جدة |
| Arabian riyal | الريال العربي |
| Wadi ar-Raml | وادي الرمل |
| Darb Zubaydah | درب زبيدة |
| Hajj economy | اقتصاد الحج |
| Al-Ghabah | الغابة |
| nahham blues | بلوز النهّام |
| kabsa and qahwa | الكبسة والقهوة |
| saqr / madrab | الصقر / المضرب |
| Manumission Day | يوم العتق |
| European Arabians | العرب الأوروبيون |
