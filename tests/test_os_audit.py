from tools.os_audit import fixes_for


def test_available_fixes_are_specific_to_distribution_package_and_newer_version():
    record={'affected':[{'package':{'name':'lib','ecosystem':'Debian:13'},'ranges':[{'events':[{'introduced':'0'},{'fixed':'2'}]}]}]}
    less=lambda a,b:int(a)<int(b)
    assert fixes_for(record,'lib','1','Debian:13',less)==['2']
    assert fixes_for(record,'lib','3','Debian:13',less)==[]
    assert fixes_for(record,'other','1','Debian:13',less)==[]
    assert fixes_for(record,'lib','1','Debian:12',less)==[]
    assert fixes_for({**record,'withdrawn':'2026-01-01'},'lib','1','Debian:13',less)==[]


def test_no_fix_remains_explicit_review_item_not_invented_fix():
    record={'affected':[{'package':{'name':'lib','ecosystem':'Debian:13'},'ranges':[{'events':[{'introduced':'0'}]}]}]}
    assert fixes_for(record,'lib','1','Debian:13',lambda a,b:True)==[]
