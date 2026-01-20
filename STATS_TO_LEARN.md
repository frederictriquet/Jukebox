Ci-dessous : **set optimal minimal**, conçu pour **musique électronique multi-sous-styles**, **apprenable**, **stable**, et **non redondant**.
Ce set est volontairement limité pour maximiser le signal utile et éviter l’overfitting.
Il est prêt à être donné tel quel à une IA pour spécification.

---

# SET OPTIMAL — FEATURES AUDIO (≈45–55 features après stats)

## 1. Énergie & dynamique (≈8)

* RMS energy (mean, std)
* RMS percentiles (10, 90)
* Peak amplitude
* Crest factor
* Dynamic range
* Loudness variation (std RMS)

---

## 2. Énergie par bandes fréquentielles (≈12)

Bandes fixes :

* Sub-bass (20–60 Hz)
* Bass (60–150 Hz)
* Low-mid (150–500 Hz)
* Mid (500–2 kHz)
* High-mid (2–6 kHz)
* High / treble (6–20 kHz)

Pour chaque bande :

* Mean energy
* Energy ratio (bande / total)

---

## 3. Timbre & texture spectrale (≈8)

* Spectral centroid (mean, std)
* Spectral bandwidth (mean)
* Spectral rolloff (mean)
* Spectral flatness (mean)
* Spectral contrast (mean)
* Spectral entropy (mean)

---

## 4. Texture MFCC (≈10)

* MFCC (coefficients 1–10)
* MFCC mean (par coeff.)

*(pas de delta ici : redondant à ce niveau de compacité)*

---

## 5. Percussif vs harmonique (≈5)

* Percussive energy (mean)
* Harmonic energy (mean)
* Percussive / harmonic ratio
* Percussive onset rate
* Onset strength mean

---

## 6. Rythme & tempo (≈6)

* Global tempo (BPM)
* Tempo confidence
* Beat interval mean
* Beat interval std (stabilité)
* Onset rate (onsets/sec)
* Tempogram dominant periodicity

---

## 7. Harmonie simplifiée (≈4)

* Chroma entropy
* Chroma centroid
* Chroma energy std
* Tonnetz mean energy

---

## 8. Structure DJ minimale (≈4)

* Intro energy ratio (first 20–30 %)
* Core energy ratio
* Outro energy ratio
* Energy slope (global)

---

# TOTAL APPROXIMATIF

* **Features brutes** : ~35
* **Après stats essentielles** : **45–55 dimensions**

➡️ Zone optimale pour :

* Random Forest
* XGBoost
* SVM
* Clustering (UMAP + HDBSCAN)

---

## Ce set exclut volontairement

* Pitch tracking fin
* MFCC delta/delta-delta
* Spectrogrammes bruts
* Descripteurs vocaux
* Features trop corrélées (ZCR, rolloff multiples, etc.)

---

## Pourquoi ce set est optimal (factuel)

* Forte **invariance aux variations de mix/mastering**
* Sensible aux **différences de sous-styles électro**
* Stable sur **intros/outros DJ**
* Suffisant pour **classification, clustering, recommandation**

---

Si tu veux aller plus loin :

* je peux produire une **spécification strictement formelle** (noms, types, ranges),
* ou challenger ce set **par rapport à TES catégories existantes** (quelles labels sont réellement apprenables).
