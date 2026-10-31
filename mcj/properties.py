"""Java properties escaping, including the escapes written back by Minecraft."""
import re

def unescape(value):
    result=[];i=0
    while i<len(value):
        char=value[i];i+=1
        if char!='\\':result.append(char);continue
        if i==len(value):break
        char=value[i];i+=1
        if char=='u':
            digits=value[i:i+4]
            if not re.fullmatch('[0-9A-Fa-f]{4}',digits):raise ValueError('invalid_properties_unicode_escape')
            result.append(chr(int(digits,16)));i+=4
        else:result.append({'n':'\n','r':'\r','t':'\t','f':'\f'}.get(char,char))
    # Java permits UTF-16 surrogate pairs in \u escapes.
    return ''.join(result).encode('utf-16','surrogatepass').decode('utf-16')

def loads(text):
    result={};pending=''
    # java.util.Properties recognizes only LF, CR and CRLF as physical line
    # endings.  str.splitlines() also splits on characters such as VT, NEL and
    # the Unicode line separators, which can make validation disagree with the
    # Minecraft JVM about the effective value of a security-sensitive key.
    for physical in re.split(r'\r\n|[\r\n]',text):
        line=pending+physical.lstrip(' \t\f') if pending else physical
        trailing=len(line)-len(line.rstrip('\\'))
        if trailing%2:pending=line[:-1];continue
        pending='';line=line.lstrip(' \t\f')
        if not line or line[0] in '#!':continue
        escaped=False;split=len(line)
        for i,char in enumerate(line):
            if not escaped and char in '=:\t\f ':split=i;break
            escaped=(not escaped) if char=='\\' else False
        value=split
        while value<len(line) and line[value] in ' \t\f':value+=1
        if value<len(line) and line[value] in '=:':value+=1
        while value<len(line) and line[value] in ' \t\f':value+=1
        result[unescape(line[:split])]=unescape(line[value:])
    if pending:
        # A final continuation at EOF behaves as an empty following physical line.
        result.update(loads(pending+'\n'))
    return result

def escape(value,key=False):
    result=[]
    for i,char in enumerate(str(value)):
        replacement={'\\':'\\\\','\n':'\\n','\r':'\\r','\t':'\\t','\f':'\\f'}.get(char)
        if replacement is not None:result.append(replacement)
        elif char in '=:' and key or char in '#!' or char==' ' and (key or i==0):result.append('\\'+char)
        else:result.append(char)
    return ''.join(result)

def dumps(values):
    return ''.join(escape(key,True)+'='+escape(value)+'\n' for key,value in values.items())
