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
- **Untranslated targets:** a link to an article that has no Arabic edition yet
  points at `../<file>.html` and carries `class="pending"`, which prints
  "(بالإنجليزية)" after it, the way an interlanguage red link behaves. When the
  Arabic edition of that article lands, drop `../` and drop the class.

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

## Nations and polities

| English | العربية | Carries |
|---|---|---|
| United States of Arabia | الولايات المتحدة العربية | the United States |
| — short form | الولايات المتحدة | never «العربية» alone, which reads as the language |
| al-Mashriq | المشرق | |
| Zagrosia | زاغروسيا | Canada |
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
| Cape Republic | جمهورية الكاب | Turkey |
| Kanem | كانم | custom (Chad) |
| Songhai | سنغاي | custom |
| Tem | تم | custom |

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
| OTL / the outside timeline | الخط الزمني الخارجي |
| Motor vehicles | المركبات الآلية |

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
