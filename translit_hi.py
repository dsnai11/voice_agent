"""Devanagari -> Hinglish Roman (the spelling the fine-tuned voice was trained on)."""
import re
V={"अ":"a","आ":"aa","इ":"i","ई":"i","उ":"u","ऊ":"u","ऋ":"ri","ए":"e","ऐ":"ai","ओ":"o","औ":"au","ऑ":"o","ऍ":"e"}
M={"ा":"aa","ि":"i","ी":"i","ु":"u","ू":"u","ृ":"ri","े":"e","ै":"ai","ो":"o","ौ":"au","ॉ":"o","ॅ":"e"}
C={"क":"k","ख":"kh","ग":"g","घ":"gh","ङ":"n","च":"ch","छ":"chh","ज":"j","झ":"jh","ञ":"n","ट":"t","ठ":"th","ड":"d","ढ":"dh","ण":"n","त":"t","थ":"th","द":"d","ध":"dh","न":"n","प":"p","फ":"ph","ब":"b","भ":"bh","म":"m","य":"y","र":"r","ल":"l","व":"v","श":"sh","ष":"sh","स":"s","ह":"h","क़":"q","ख़":"kh","ग़":"g","ज़":"z","ड़":"r","ढ़":"rh","फ़":"f"}
NUK="़";VIR="्";ANU={"ं":"n","ँ":"n","ः":"h"}
def _word(w):
    w=w.replace("क़","क़").replace("ख़","ख़").replace("ग़","ग़").replace("ज़","ज़").replace("ड़","ड़").replace("ढ़","ढ़").replace("फ़","फ़")
    out=[];i=0;n=len(w)
    while i<n:
        ch=w[i]
        if ch in C:
            c=C[ch];j=i+1
            if j<n and w[j]==VIR: out.append((c,"c"));i=j+1;continue
            if j<n and w[j] in M: out.append((c+M[w[j]],"m"));i=j+1;continue
            out.append((c+"a","s"));i=j;continue          # inherent a (maybe dropped below)
        if ch in V: out.append((V[ch],"v"));i+=1;continue
        if ch in ANU:
            if out: out[-1]=(out[-1][0]+ANU[ch],out[-1][1])
            i+=1;continue
        out.append((ch,"o"));i+=1
    for k in range(len(out)-1,0,-1):
        s,t=out[k]
        if t=="s" and s.endswith("a"):
            if k==len(out)-1: out[k]=(s[:-1],"c")
            elif k<len(out)-1 and out[k-1][1] in "msv" and out[k+1][1] in "msv": out[k]=(s[:-1],"c")
    txt="".join(s for s,_ in out)
    txt=re.sub(r"n(?=[pb])","m",txt)
    if len(txt)>3: txt=re.sub(r"aa$","a",txt)
    txt=txt.replace("aai","ai") if False else txt
    return txt
DICT={"रिया":"Riya","लक्ष्मी":"Lakshmi","इंडिया":"India","फाइनेंस":"Finance","लिमिटेड":"Limited","लोन":"loan","नंबर":"number","बैंक":"bank","अकाउंट":"account","ईएमआई":"EMI","टीम":"team","नोट":"note","टाइम":"time","ठीक":"theek","कृपया":"kripya","जी":"ji","हूँ":"hoon","हूं":"hoon","मैं":"main","है":"hai","हैं":"hain","नहीं":"nahin","ब्रांच":"branch","कॉल":"call","ऑनलाइन":"online","पेमेंट":"payment","स्टेटमेंट":"statement","सर":"sir","मैम":"madam","इंटरेस्ट":"interest","डॉक्यूमेंट":"document","डॉक्यूमेंट्स":"documents","कस्टमर":"customer","एनओसी":"NOC","नमस्ते":"namaste","धन्यवाद":"dhanyavaad"}
def roman(text):
    text=text.replace("।",".").replace("॥",".")
    t=re.sub(r"[ऀ-ॿ]+",lambda m:DICT.get(m.group(0)) or _word(m.group(0)),text)
    t=re.sub(r"(?<=[a-z])ie\b","iye",t)
    t=re.sub(r"\s+"," ",t).strip()
    t=re.sub(r"(^|[.?!] )([a-z])",lambda m:m.group(1)+m.group(2).upper(),t)
    if t and t[-1] not in ".?!": t+="."
    return t
if __name__=="__main__":
    import sys;sys.stdout.reconfigure(encoding="utf-8")
    for t in ["नमस्ते, मैं रिया बोल रही हूँ, लक्ष्मी इंडिया फाइनेंस लिमिटेड से।","जी, किस्त आपके बैंक अकाउंट से कटती है। अपना लोन नंबर बता दीजिए।","ठीक है जी, आपकी जानकारी नोट हो गई है और हमारी टीम जल्दी आपसे संपर्क करेगी।","कृपया अपना पूरा नाम बताइए।"]:
        print(roman(t))
