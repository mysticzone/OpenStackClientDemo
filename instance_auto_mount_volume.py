#!/usr/bin/env python


from cinderclient import client as cinderclient
from glanceclient import Client as glanceclient
from keystoneclient.auth.identity import v2
from keystoneclient import session
from novaclient import client as novaclient

import time


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

## cloud.pub.key
# Use `ssh-keygen -t rsa -f cloud.key` generate key
pub_key_name = "cloud_key_pub"
cloud_key_pub_file = "/home/stack/cloud.key.pub"
cloud_pub_key = open(cloud_key_pub_file, "r").read().strip()


# User data
user_ops = """#!/usr/bin/env bash

LABLE=$(sudo lsblk | grep vdb | cut -c -3)

for i in $(seq 1 60)
do
    sleep 2
    if [ -n $LABLE ]; then
        sudo mkfs.ext4 /dev/vdb
        sudo mount /dev/vdb /mnt
        exit 0
    fi
done
"""

def get_network_id():
    networks = nova.networks.list()
    network_id = networks[0].id
    return network_id

def volume_create_or_delete(flag=True):
    if True == flag:
        volume = cinder.volumes.create(name=volume_name, size=volume_size)
        volume_id = volume.id

        #time.sleep(6)
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
        return flavor_id
    else:
        flavors = nova.flavors.list()
        for item in flavors:
            if item.name == flavor_name:
                flavor_id = item.id
                nova.flavors.delete(flavor_id)
                print "The flavor %s has been deleted!" % flavor_id

def instance_create_or_delete(flag=True):
    if True == flag:
        get_flavor_id = flavor_create_or_delete()
        get_image_id = image_upload_or_drop()
        instance = nova.servers.create(vm_name,
                                       get_image_id,
                                       get_flavor_id,
                                       key_name=pub_key_name,
                                       userdata=user_ops,
                                       nics=[{'net-id': get_network_id()}])
        #time.sleep(30)
        instance_id = instance.id
        print "The instance %s has been created successfully!" % (instance_id)
        return instance_id
    else:
        vms = nova.servers.list()
        for item in vms:
            nova.servers.delete(item.id)
            time.sleep(15)
            print "The instance %s has been deleted!" % (item.id)


def keys_create_or_delete(flag=True):
    if True == flag:
        nova.keypairs.create(pub_key_name, public_key=cloud_pub_key)
        print "The %s has been created!" % (pub_key_name)
    else:
        keys = nova.keypairs.list()
        for key in keys:
            if key.name == pub_key_name:
                nova.keypairs.delete(key.id)
                print "The %s have been deleted!" % (pub_key_name)
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
    print "The volume %s has mount to instance %s." % (volume_name, vm_name)

def allocate_fip_to_instance(instance, flag=True):
    fip = nova.floating_ips.create(pool="public")
    nova.servers.add_floating_ip(instance, fip.ip)
    print "The %s has allocated to the instance %s." % (fip.ip, instance)

def clean_all(flag=False):
    instance_create_or_delete(flag)
    flavor_create_or_delete(flag)

    # delete floating_ips
    fips = nova.floating_ips.list()
    for fip in fips:
        nova.floating_ips.delete(fip.id)
        print "Floating ip %s has been deleted." % (fip.ip)

    image_upload_or_drop(flag)
    keys_create_or_delete(flag)
    volume_create_or_delete(flag)


def main():
    print "All clean everthing!"
    clean_all()

    get_volume_id = volume_create_or_delete()
    for count in range(0, timeout):
        time.sleep(1)
        vols = cinder.volumes.list()
        for vol in vols:
            print "The current state of the %s is %s." % (vol.name, vol.status)
            if vol.name == volume_name:
                break
        if vol.status == "available":
            print "break", vol.status
            break

    print "The %s has finished!" % (get_volume_id)
    keys_create_or_delete()

    get_instance_id = instance_create_or_delete()

    for count in range(0, timeout):
        time.sleep(1)
        vms = nova.servers.list()
        for vm in vms:
            print "The current state of the %s is %s" % (vm_name, vm.status)
            if vm.name == vm_name:
                break
        if vm.status == "ACTIVE":
            # print "break", vm.status
            break

    allocate_fip_to_instance(get_instance_id)
    print "The %s instance has finished!" % (get_instance_id)

    mount_volume_to_instance(get_instance_id, get_volume_id)
    print "The volume %s has mounted to the instance %s" % (get_instance_id, get_volume_id)


if __name__=="__main__":
    main()

