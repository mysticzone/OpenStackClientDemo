#!/usr/bin/env python

from cinderclient import client as cinderclient
from glanceclient import Client as glanceclient
from keystoneclient.auth.identity import v2
from keystoneclient import session
from novaclient import client as novaclient

import time
import os

AUTH_URL = "http://200.21.4.45:5000/v2.0"
USERNAME = "admin"
PASSWORD = "yanghaosysadmin"
PROJECT_NAME = "admin"

auth = v2.Password(auth_url=AUTH_URL,
                   username=USERNAME,
                   password=PASSWORD,
                   tenant_name=PROJECT_NAME)
sess = session.Session(auth=auth)
nova = novaclient.Client("2", session=sess)

OS_IMAGE_ENDPOINT = auth.get_endpoint(sess, interface="public", service_type="image")
OS_AUTH_TOKEN = auth.get_token(sess)

# Glance Identity
glance = glanceclient('2', endpoint=OS_IMAGE_ENDPOINT, token=OS_AUTH_TOKEN)

# Cinder Identity
cinder = cinderclient.Client("2",
                             USERNAME,
                             PASSWORD,
                             PROJECT_NAME,
                             AUTH_URL)

# Time Out
timeout = 120

# Instance Name
vm_name = "test1"

# Define Flavor
flavor_name = "2U2G20"
flavor_mem = 2048
flavor_cpu = 2
flavor_disk = 20

# Image Information
image_name = "Test Image"
image_path = "/home/stack/trusty-server-cloudimg-amd64-disk1.img"

# Define Volume
volume_size=2
volume_name="test-vol"

## Generate keyparis
key_name_pub = "cloud_pub_key"
key_name_pri = "cloud_pri_key"


def get_network_id():
    networks = nova.networks.list()
    network_id = networks[0].id
    return network_id

def volume_create_or_delete(flag=True):
    if True == flag:
        volume = cinder.volumes.create(name=volume_name, size=volume_size)
        volume_id = volume.id

        print "The volume %s has been created!" % (volume_id)
        return volume_id
    else:
        volumes = cinder.volumes.list()
        for volume in volumes:
            if volume.name == volume_name:
                cinder.volumes.delete(volume.id)
                print "The volume %s has been deleted successfully!" % (volume_name)

def flavor_create_or_delete(flag=True):
    if True == flag:
        flavor = nova.flavors.create(flavor_name,
                                     flavor_mem,
                                     flavor_cpu,
                                     flavor_disk)
        flavor_id = flavor.id
        print "The flavor %s has been created!" % flavor_id
        return flavor_id
    else:
        flavors = nova.flavors.list()
        for item in flavors:
            if item.name == flavor_name:
                flavor_id = item.id
                nova.flavors.delete(flavor_id)
                print "The flavor %s has been deleted!" % flavor_id

def instance_create_or_delete(flag=True):
    instance_id = None
    if True == flag:
        # Create flavor
        get_flavor_id = flavor_create_or_delete()
        # Upload image
        get_image_id = image_upload_or_drop()
        instance = nova.servers.create(vm_name,
                                       get_image_id,
                                       get_flavor_id,
                                       key_name=key_name_pub,
                                       nics=[{'net-id': get_network_id()}])
        instance_id = instance.id
        print "The instance %s has been created!" % (instance_id)
        return instance_id
    else:
        vms = nova.servers.list()
        # Delete the instance
        for vm in vms:
            if vm.name == vm_name:
                instance_id = vm.id
                nova.servers.delete(instance_id)
                print "The instance %s has been deleted!" % (instance_id)
                break
        return instance_id

def keys_create_or_delete(flag=True):
    if True == flag:
        keypairs = nova.keypairs.create(key_name_pub)
        fp = os.open(key_name_pri, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fp, 'w') as f:
                 f.write(keypairs.private_key)
        print "The %s has been created!" % (key_name_pub)
    else:
        keys = nova.keypairs.list()
        for key in keys:
            if key.name == key_name_pub:
                nova.keypairs.delete(key.id)
                print "The %s have been deleted!" % (key_name_pub)
                break

def image_upload_or_drop(flag=True):
    if True == flag:
        image = glance.images.create(name=image_name,
                                     disk_format="qcow2",
                                     container_format="bare",
                                     visibility="public")
        glance.images.upload(image.id, open(image_path, "rb"))
        print "The image %s has been uploaded!" % image_path.split("/")[3]
        return image.id
    else:
        images = glance.images.list()
        try:
            while True:
                image = images.next()
                if image["name"] == image_name:
                    glance.images.delete(image["id"])
                    print "The image %s has been deleted!" % (image_name)
        except StopIteration:
            pass

def mount_volume_to_instance(instance, volume):
    nova.volumes.create_server_volume(instance, volume, "/dev/vdb")
    print "The volume %s has mount to instance %s!" % (volume_name, vm_name)

def allocate_fip_to_instance(instance, flag=True):
    fip = nova.floating_ips.create(pool="public")
    nova.servers.add_floating_ip(instance, fip.ip)
    print "The %s has allocated to the instance %s!" % (fip.ip, instance)
    return fip.ip

def format_mount_volume(fip):
    comm = 'ssh -i cloud_pri_key -o StrictHostKeyChecking=no ubuntu@%s "sudo mkfs.ext4 /dev/vdb && sudo mount /dev/vdb /mnt"' % (fip)
    print "Formatting a disk /dev/vdb, and mount it to /mnt."

    while True:
        ret = os.system(comm)
        if ret == 0:
            break
        else:
            time.sleep(2)
            continue

# All clean resource
def clean_all(flag=False):
    instance_id = instance_create_or_delete(flag)
    flavor_create_or_delete(flag)

    image_upload_or_drop(flag)
    keys_create_or_delete(flag)

    # Delete floating_ips
    fips = nova.floating_ips.list()
    for fip in fips:
        if fip.instance_id == instance_id:
            nova.floating_ips.delete(fip.id)
            print "Floating ip %s has been deleted!" % (fip.ip)
            break

    # Waiting instance to be deleted
    while True:
        vms = nova.servers.list()
        for vm in vms:
            if vm.id == instance_id:
                print "Waiting for the instance %s to be deleted!" % (instance_id)
                time.sleep(1)
                break
        else:
            print "The instance %s has been deleted!" % (instance_id)
            break

    # Delete volume
    volume_create_or_delete(flag)

def main():
    print "All clean everthing...."
    clean_all()

    # Generate keypairs
    keys_create_or_delete()

    # Create instance
    get_instance_id = instance_create_or_delete()

    # Create volume
    get_volume_id = volume_create_or_delete()

    # Check volume status
    for count in range(0, timeout):
        time.sleep(1)
        vols = cinder.volumes.list()
        for vol in vols:
            print "The current state of the %s is %s!" % (vol.name, vol.status)
            if vol.id == get_volume_id:
                break
        if vol.status == "available":
            break

    # Check instance volume
    for count in range(0, timeout):
        time.sleep(1)
        vms = nova.servers.list()
        for vm in vms:
            print "The current state of the %s is %s" % (vm_name, vm.status)
            if vm.id == get_instance_id:
                break
        if vm.status == "ACTIVE":
            break

    # Allocate floating ip to instance
    floating_ip = allocate_fip_to_instance(get_instance_id)

    for count in range(0, timeout):
        time.sleep(1)
        fips = nova.floating_ips.list()
        for fip in fips:
            print "Floating ip %s allocate to instance %s!" % (floating_ip, get_instance_id)
            if fip.ip == floating_ip:
                break
        if fip.instance_id is not None:
            break

    # Attach volume to instance
    mount_volume_to_instance(get_instance_id, get_volume_id)
    print "The volume %s has mounted to the instance %s!" % (get_instance_id, get_volume_id)

    # Detection mounted volume status
    for count in range(0, timeout):
        time.sleep(1)
        vols = cinder.volumes.list()
        for vol in vols:
            print "The current state of the %s is %s!" % (vol.name, vol.status)
            if vol.id == get_volume_id:
                break
        if vol.status == "in-use":
            break

    # Format and mount volume
    format_mount_volume(floating_ip)

if __name__=="__main__":
    main()
